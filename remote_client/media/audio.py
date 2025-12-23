"""Microphone audio track for WebRTC streaming."""
from __future__ import annotations

import asyncio

from aiortc import MediaStreamTrack
from av.audio.frame import AudioFrame


class AudioTrack(MediaStreamTrack):
    """Audio track reading from the system microphone."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        import sounddevice as sd

        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

        def callback(indata, frames, time, status) -> None:
            self._queue.put_nowait(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=48000,
            blocksize=960,
            dtype="int16",
            channels=1,
            callback=callback,
        )
        self._stream.start()

    async def recv(self) -> AudioFrame:
        data = await self._queue.get()
        frame = AudioFrame(format="s16", layout="mono", samples=len(data) // 2)
        frame.planes[0].update(data)
        frame.sample_rate = 48000
        return frame
