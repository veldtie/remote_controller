"""Screen capture track for WebRTC video streaming."""
from __future__ import annotations

from aiortc import VideoStreamTrack
from av import VideoFrame


class ScreenTrack(VideoStreamTrack):
    """Video track that captures the primary monitor."""

    def __init__(self) -> None:
        super().__init__()
        import mss
        import numpy as np

        self._np = np
        self._sct = mss.mss()
        self._monitor = self._sct.monitors[1]

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        img = self._np.array(self._sct.grab(self._monitor))
        frame = VideoFrame.from_ndarray(img[:, :, :3], format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame
