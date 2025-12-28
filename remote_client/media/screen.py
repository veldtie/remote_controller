"""Screen capture track for WebRTC video streaming."""
from __future__ import annotations

import os
import platform

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

        if platform.system() == "Windows" or os.getenv("DISPLAY"):
            try:
                self._sct = mss.mss()
                self._monitor = self._sct.monitors[1]
                self._frame_size = (self._monitor["width"], self._monitor["height"])
            except Exception:
                self._sct = None
                self._monitor = None

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        if self._sct is None or self._monitor is None:
            width, height = self._frame_size
            img = self._np.zeros((height, width, 3), dtype=self._np.uint8)
        else:
            img = self._np.array(self._sct.grab(self._monitor))[:, :, :3]
        frame = VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame
