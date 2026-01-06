"""Screen capture track for WebRTC video streaming."""
from __future__ import annotations

import ctypes
import os
import platform
from ctypes import wintypes

from aiortc import VideoStreamTrack
from av import VideoFrame


class ScreenTrack(VideoStreamTrack):
    """Video track that captures the primary monitor."""

    def __init__(self) -> None:
        super().__init__()
        import mss
        import numpy as np

        self._np = np
        self._sct = None
        self._monitor = None
        self._frame_size = (1280, 720)
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

        self._setup_cursor()

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        if self._sct is None or self._monitor is None:
            width, height = self._frame_size
            img = self._np.zeros((height, width, 3), dtype=self._np.uint8)
        else:
            img = self._np.array(self._sct.grab(self._monitor))[:, :, :3]
        self._draw_cursor(img)
        frame = VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
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
