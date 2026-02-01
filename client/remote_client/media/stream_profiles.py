from __future__ import annotations

from collections import deque
import time
from typing import Deque


STREAM_PROFILES: dict[str, dict[str, int]] = {
    "speed": {"min_height": 720, "max_height": 1080, "min_fps": 40, "max_fps": 60},
    "balanced": {"min_height": 900, "max_height": 1440, "min_fps": 30, "max_fps": 60},
    "quality": {"min_height": 1080, "max_height": 2160, "min_fps": 30, "max_fps": 60},
    "reading": {"min_height": 1440, "max_height": 2160, "min_fps": 10, "max_fps": 15},
}

ADAPT_INTERVAL_SEC = 2.0
FPS_SAMPLE_SIZE = 24
FPS_STEP = 5
HEIGHT_DOWN_SCALE = 0.85
HEIGHT_UP_SCALE = 1.1


def scale_to_fit(
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


def resolve_profile_bounds(
    native_height: int,
    profile: str,
) -> tuple[int, int, int, int]:
    preset = STREAM_PROFILES.get(profile)
    if not preset:
        raise ValueError(f"Unknown stream profile '{profile}'.")
    max_height = min(preset["max_height"], native_height)
    min_height = min(preset["min_height"], max_height)
    return min_height, max_height, preset["min_fps"], preset["max_fps"]


def height_to_size(native_size: tuple[int, int], height: int) -> tuple[int, int]:
    native_width, native_height = native_size
    if native_height <= 0:
        return native_size
    scale = height / native_height
    return max(1, int(native_width * scale)), max(1, int(native_height * scale))


class AdaptiveStreamProfile:
    """Keep track of adaptive stream profile settings."""

    def __init__(self, native_size: tuple[int, int], profile: str = "balanced") -> None:
        self.native_size = native_size
        self.profile_name = "balanced"
        self.min_height = 0
        self.max_height = 0
        self.min_fps = 0
        self.max_fps = 0
        self.target_height = 0
        self.target_fps = 0
        self.hint_max_height = 0
        self.hint_max_fps = 0
        self.target_size = native_size
        self.fps_samples: Deque[float] = deque(maxlen=FPS_SAMPLE_SIZE)
        self.last_adjust_ts = 0.0
        self.apply_profile(profile=profile)

    def apply_profile(
        self,
        profile: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
    ) -> None:
        if profile:
            normalized = profile.strip().lower()
            (
                self.min_height,
                self.max_height,
                self.min_fps,
                self.max_fps,
            ) = resolve_profile_bounds(self.native_size[1], normalized)
            self.profile_name = normalized
            self.target_height = self.max_height
            self.target_fps = self.max_fps
            self.hint_max_height = self.max_height
            self.hint_max_fps = self.max_fps
            self.fps_samples.clear()
            self.last_adjust_ts = 0.0
        if width or height:
            resolved = scale_to_fit(self.native_size, width, height)
            self.hint_max_height = max(self.min_height, min(self.max_height, resolved[1]))
            if self.target_height > self.hint_max_height:
                self.target_height = self.hint_max_height
        if fps:
            self.hint_max_fps = max(self.min_fps, min(self.max_fps, fps))
            if self.target_fps > self.hint_max_fps:
                self.target_fps = self.hint_max_fps
        self.target_height = max(self.min_height, min(self.target_height, self.max_height))
        self.target_size = height_to_size(self.native_size, self.target_height)

    def add_fps_sample(self, elapsed: float) -> None:
        if elapsed > 0:
            self.fps_samples.append(1.0 / elapsed)

    def maybe_adjust(self, processing_time: float, now: float | None = None) -> bool:
        if not self.fps_samples:
            return False
        current = time.monotonic() if now is None else now
        if current - self.last_adjust_ts < ADAPT_INTERVAL_SEC:
            return False
        if self.target_fps <= 0:
            return False
        avg_fps = sum(self.fps_samples) / len(self.fps_samples)
        effective_max_height = min(self.max_height, self.hint_max_height)
        effective_max_fps = min(self.max_fps, self.hint_max_fps)
        target_interval = 1.0 / self.target_fps
        underperform = avg_fps < self.target_fps * 0.85
        headroom = avg_fps >= self.target_fps * 0.98 and processing_time < target_interval * 0.6
        old_fps = self.target_fps
        if underperform:
            if self.target_fps > self.min_fps:
                self.target_fps = max(self.min_fps, self.target_fps - FPS_STEP)
            elif self.target_height > self.min_height:
                self.target_height = max(self.min_height, int(self.target_height * HEIGHT_DOWN_SCALE))
                self.target_size = height_to_size(self.native_size, self.target_height)
            self.last_adjust_ts = current
            return self.target_fps != old_fps
        if headroom:
            if self.target_height < effective_max_height:
                self.target_height = min(effective_max_height, int(self.target_height * HEIGHT_UP_SCALE))
                self.target_size = height_to_size(self.native_size, self.target_height)
            elif self.target_fps < effective_max_fps:
                self.target_fps = min(effective_max_fps, self.target_fps + FPS_STEP)
            self.last_adjust_ts = current
            return self.target_fps != old_fps
        return False
