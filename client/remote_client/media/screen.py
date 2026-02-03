"""Screen capture track for WebRTC streaming."""
from __future__ import annotations

import asyncio
import logging
import time
from fractions import Fraction

from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError, VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
from av.video.frame import VideoFrame

from remote_client.media.stream_profiles import AdaptiveStreamProfile


logger = logging.getLogger(__name__)


class ScreenTrack(MediaStreamTrack):
    """Capture the primary screen for WebRTC streaming."""

    kind = "video"

    def __init__(
        self,
        monitor: int | None = None,
        draw_cursor: bool = True,
        profile: str = "balanced",
    ) -> None:
        super().__init__()
        self._monitor_index = monitor
        self._draw_cursor = draw_cursor
        self._sct = None
        self._monitor = None
        self._native_size = (1280, 720)
        self._profile = None
        self._target_size = self._native_size
        self._target_fps = 30
        self._last_frame_ts: float | None = None
        self._start: float | None = None
        self._timestamp = 0
        self._init_capture()
        self._profile = AdaptiveStreamProfile(self._native_size, profile=profile)
        self._apply_profile_settings()

    def _init_capture(self) -> None:
        try:
            import mss
        except Exception as exc:
            logger.warning("mss unavailable: %s", exc)
            return
        try:
            self._sct = mss.mss()
            monitors = self._sct.monitors
            if not monitors:
                return
            index = self._monitor_index
            if index is None:
                index = 1 if len(monitors) > 1 else 0
            if index < 0 or index >= len(monitors):
                index = 1 if len(monitors) > 1 else 0
            self._monitor = monitors[index]
            self._native_size = (
                int(self._monitor["width"]),
                int(self._monitor["height"]),
            )
        except Exception as exc:
            logger.warning("Screen capture init failed: %s", exc)
            self._sct = None
            self._monitor = None

    def _apply_profile_settings(self) -> None:
        if not self._profile:
            return
        self._target_size = self._profile.target_size
        self._target_fps = self._profile.target_fps

    def set_profile(
        self,
        profile: str | None,
        width: int | None,
        height: int | None,
        fps: int | None,
    ) -> None:
        if not self._profile:
            return
        self._profile.apply_profile(profile, width, height, fps)
        self._apply_profile_settings()

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

    def _frame_from_mss(self, shot) -> VideoFrame:
        frame = VideoFrame(width=shot.width, height=shot.height, format="bgra")
        frame.planes[0].update(shot.raw)
        return frame

    def _blank_frame(self) -> VideoFrame:
        width, height = self._target_size
        frame = VideoFrame(width=width, height=height, format="bgr24")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        return frame

    def _capture_frame(self) -> VideoFrame:
        if self._sct and self._monitor:
            try:
                shot = self._sct.grab(self._monitor)
                frame = self._frame_from_mss(shot)
                if (
                    self._target_size
                    and (frame.width, frame.height) != self._target_size
                ):
                    frame = frame.reformat(
                        width=self._target_size[0],
                        height=self._target_size[1],
                    )
                return frame
            except Exception as exc:
                logger.debug("Screen grab failed: %s", exc)
        return self._blank_frame()

    async def recv(self) -> VideoFrame:
        pts, time_base = await self._next_timestamp()
        start = time.monotonic()
        frame = self._capture_frame()
        now = time.monotonic()
        if self._profile:
            if self._last_frame_ts is not None:
                self._profile.add_fps_sample(now - self._last_frame_ts)
            self._last_frame_ts = now
            if self._profile.maybe_adjust(now - start, now=now):
                self._apply_profile_settings()
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def stop(self) -> None:
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
        super().stop()
