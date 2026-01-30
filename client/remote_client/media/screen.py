"""Screen capture track for WebRTC video streaming."""
from __future__ import annotations

import asyncio
import ctypes
import os
import platform
import time
from collections import deque
from ctypes import wintypes
from fractions import Fraction

from aiortc import VideoStreamTrack
from av import VideoFrame


STREAM_PROFILES: dict[str, dict[str, int]] = {
    "speed": {"min_height": 720, "max_height": 1080, "min_fps": 40, "max_fps": 60},
    "balanced": {"min_height": 900, "max_height": 1440, "min_fps": 30, "max_fps": 60},
    "quality": {"min_height": 1080, "max_height": 2160, "min_fps": 30, "max_fps": 60},
    "reading": {"min_height": 1440, "max_height": 2160, "min_fps": 10, "max_fps": 20},
}
ADAPT_INTERVAL_SEC = 2.0
FPS_SAMPLE_SIZE = 24
FPS_STEP = 5
HEIGHT_DOWN_SCALE = 0.85
HEIGHT_UP_SCALE = 1.1
VIDEO_TIME_BASE = Fraction(1, 90000)


def _scale_to_fit(
    size: tuple[int, int],
    max_width: int | None,
    max_height: int | None,
) -> tuple[int, int]:
    width, height = size
    scale = 1.0
    if max_width:
        scale = min(scale, max_width / width)
    if max_height:
        scale = min(scale, max_height / height)
    if scale >= 1.0:
        return size
    return max(1, int(width * scale)), max(1, int(height * scale))


def _resolve_profile_bounds(
    native_height: int,
    profile: str,
) -> tuple[int, int, int, int]:
    preset = STREAM_PROFILES.get(profile)
    if not preset:
        raise ValueError(f"Unknown stream profile '{profile}'.")
    max_height = min(preset["max_height"], native_height)
    min_height = min(preset["min_height"], max_height)
    return min_height, max_height, preset["min_fps"], preset["max_fps"]


def _height_to_size(native_size: tuple[int, int], height: int) -> tuple[int, int]:
    native_width, native_height = native_size
    if native_height <= 0:
        return native_size
    scale = height / native_height
    return max(1, int(native_width * scale)), max(1, int(native_height * scale))


class ScreenTrack(VideoStreamTrack):
    """Video track that captures the primary monitor."""

    def __init__(self, draw_cursor: bool = True) -> None:
        super().__init__()
        import mss
        import numpy as np

        self._np = np
        self._sct = None
        self._monitor = None
        self._frame_size = (1280, 720)
        self._draw_cursor_enabled = draw_cursor
        self._cursor_enabled = False
        self._cursor_info = None
        self._get_cursor_info = None
        self._cursor_showing_flag = 0x00000001
        self._monitor_offset = (0, 0)

        if platform.system() == "Windows" or os.getenv("DISPLAY"):
            try:
                self._sct = mss.mss()
                self._monitor = self._sct.monitors[1]
                self._frame_size = (self._monitor["width"], self._monitor["height"])
                self._monitor_offset = (
                    self._monitor.get("left", 0),
                    self._monitor.get("top", 0),
                )
            except Exception:
                self._sct = None
                self._monitor = None
                self._monitor_offset = (0, 0)

        self._native_size = self._frame_size
        self._profile_name = "balanced"
        (
            self._min_height,
            self._max_height,
            self._min_fps,
            self._max_fps,
        ) = _resolve_profile_bounds(self._native_size[1], self._profile_name)
        self._target_height = self._max_height
        self._target_fps = self._max_fps
        self._hint_max_height = self._max_height
        self._hint_max_fps = self._max_fps
        self._target_size = _height_to_size(self._native_size, self._target_height)
        self._last_frame_ts: float | None = None
        self._last_adjust_ts = 0.0
        self._fps_samples: deque[float] = deque(maxlen=FPS_SAMPLE_SIZE)
        self._start_time = time.monotonic()
        self._setup_cursor()

    def set_profile(
        self,
        profile: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
    ) -> None:
        """Update stream scaling based on a named profile or dimensions."""
        if profile:
            normalized = profile.strip().lower()
            (
                self._min_height,
                self._max_height,
                self._min_fps,
                self._max_fps,
            ) = _resolve_profile_bounds(self._native_size[1], normalized)
            self._profile_name = normalized
            self._target_height = self._max_height
            self._target_fps = self._max_fps
            self._hint_max_height = self._max_height
            self._hint_max_fps = self._max_fps
            self._fps_samples.clear()
            self._last_adjust_ts = 0.0
        if width or height:
            resolved = _scale_to_fit(self._native_size, width, height)
            self._hint_max_height = max(self._min_height, min(self._max_height, resolved[1]))
            if self._target_height > self._hint_max_height:
                self._target_height = self._hint_max_height
        if fps:
            self._hint_max_fps = max(self._min_fps, min(self._max_fps, fps))
            if self._target_fps > self._hint_max_fps:
                self._target_fps = self._hint_max_fps
        self._target_height = max(self._min_height, min(self._target_height, self._max_height))
        self._target_size = _height_to_size(self._native_size, self._target_height)

    def _maybe_adjust_profile(self, processing_time: float) -> None:
        if not self._fps_samples:
            return
        now = time.monotonic()
        if now - self._last_adjust_ts < ADAPT_INTERVAL_SEC:
            return
        avg_fps = sum(self._fps_samples) / len(self._fps_samples)
        if self._target_fps <= 0:
            return
        effective_max_height = min(self._max_height, self._hint_max_height)
        effective_max_fps = min(self._max_fps, self._hint_max_fps)
        target_interval = 1.0 / self._target_fps
        underperform = avg_fps < self._target_fps * 0.85
        headroom = avg_fps >= self._target_fps * 0.98 and processing_time < target_interval * 0.6
        if underperform:
            if self._target_fps > self._min_fps:
                self._target_fps = max(self._min_fps, self._target_fps - FPS_STEP)
            elif self._target_height > self._min_height:
                self._target_height = max(self._min_height, int(self._target_height * HEIGHT_DOWN_SCALE))
                self._target_size = _height_to_size(self._native_size, self._target_height)
            self._last_adjust_ts = now
            return
        if headroom:
            if self._target_height < effective_max_height:
                self._target_height = min(effective_max_height, int(self._target_height * HEIGHT_UP_SCALE))
                self._target_size = _height_to_size(self._native_size, self._target_height)
            elif self._target_fps < effective_max_fps:
                self._target_fps = min(effective_max_fps, self._target_fps + FPS_STEP)
            self._last_adjust_ts = now

    async def recv(self) -> VideoFrame:
        target_interval = 1.0 / self._target_fps if self._target_fps else 0.0
        if self._last_frame_ts is not None and target_interval > 0.0:
            elapsed = time.monotonic() - self._last_frame_ts
            if elapsed < target_interval:
                await asyncio.sleep(target_interval - elapsed)
            elapsed = time.monotonic() - self._last_frame_ts
            if elapsed > 0:
                self._fps_samples.append(1.0 / elapsed)

        capture_start = time.monotonic()
        if self._sct is None or self._monitor is None:
            width, height = self._frame_size
            img = self._np.zeros((height, width, 3), dtype=self._np.uint8)
        else:
            img = self._np.array(self._sct.grab(self._monitor))[:, :, :3]
        if self._draw_cursor_enabled:
            self._draw_cursor(img)
        frame = VideoFrame.from_ndarray(img, format="bgr24")
        target_width, target_height = self._target_size
        if frame.width != target_width or frame.height != target_height:
            frame = frame.reformat(width=target_width, height=target_height)
        processing_time = time.monotonic() - capture_start
        self._maybe_adjust_profile(processing_time)
        self._last_frame_ts = time.monotonic()
        frame.pts = int((self._last_frame_ts - self._start_time) * 90000)
        frame.time_base = VIDEO_TIME_BASE
        return frame

    def _setup_cursor(self) -> None:
        if platform.system() != "Windows":
            return
        try:
            user32 = ctypes.windll.user32

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class CURSORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("hCursor", wintypes.HCURSOR),
                    ("ptScreenPos", POINT),
                ]

            self._cursor_info = CURSORINFO()
            self._cursor_info.cbSize = ctypes.sizeof(CURSORINFO)
            self._get_cursor_info = user32.GetCursorInfo
            self._get_cursor_info.argtypes = [ctypes.POINTER(CURSORINFO)]
            self._get_cursor_info.restype = wintypes.BOOL
            self._cursor_enabled = True
        except Exception:
            self._cursor_enabled = False

    def _draw_cursor(self, img) -> None:
        if not self._cursor_enabled or self._cursor_info is None:
            return
        self._cursor_info.cbSize = ctypes.sizeof(self._cursor_info)
        if not self._get_cursor_info(ctypes.byref(self._cursor_info)):
            return
        if not (self._cursor_info.flags & self._cursor_showing_flag):
            return
        x = int(self._cursor_info.ptScreenPos.x - self._monitor_offset[0])
        y = int(self._cursor_info.ptScreenPos.y - self._monitor_offset[1])
        height, width = img.shape[:2]
        if x < 0 or y < 0 or x >= width or y >= height:
            return
        self._draw_cross(img, x, y)

    @staticmethod
    def _draw_cross(img, x: int, y: int) -> None:
        height, width = img.shape[:2]
        size = 7
        ScreenTrack._draw_cross_lines(img, x, y, size, (0, 0, 0), thickness=3, width=width, height=height)
        ScreenTrack._draw_cross_lines(img, x, y, size, (255, 255, 255), thickness=1, width=width, height=height)

    @staticmethod
    def _draw_cross_lines(img, x: int, y: int, size: int, color, thickness: int, width: int, height: int) -> None:
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
