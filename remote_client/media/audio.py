"""Microphone audio track for WebRTC streaming."""
from __future__ import annotations

import asyncio

from aiortc import MediaStreamTrack
from av.audio.frame import AudioFrame


class AudioTrack(MediaStreamTrack):
    """Audio track reading from the system microphone."""

    kind = "audio"

    def __init__(self, timeout_s: float = 0.5) -> None:
        super().__init__()
        import sounddevice as sd

        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._timeout_s = timeout_s
        self._samplerate = 48000
        self._blocksize = 960

        def callback(indata, frames, time, status) -> None:
            self._queue.put_nowait(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self._samplerate,
            blocksize=self._blocksize,
            dtype="int16",
            channels=1,
            callback=callback,
        )
        self._stream.start()

    async def recv(self) -> AudioFrame:
        try:
            data = await asyncio.wait_for(self._queue.get(), timeout=self._timeout_s)
        except asyncio.TimeoutError:
            data = b""

        if not data:
            data = b"\x00" * (self._blocksize * 2)

        frame = AudioFrame(format="s16", layout="mono", samples=len(data) // 2)
        frame.planes[0].update(data)
        frame.sample_rate = self._samplerate
        return frame
