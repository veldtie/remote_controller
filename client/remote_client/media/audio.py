"""Microphone audio track for WebRTC streaming."""
from __future__ import annotations

import asyncio
import ctypes.util
import struct
from fractions import Fraction

from aiortc import MediaStreamTrack
from av.audio.frame import AudioFrame


class AudioTrack(MediaStreamTrack):
    """Audio track reading from the system microphone."""

    kind = "audio"

    def __init__(self, timeout_s: float = 0.5) -> None:
        super().__init__()
        if ctypes.util.find_library("portaudio") is None:
            self._queue = asyncio.Queue()
            self._timeout_s = timeout_s
            self._samplerate = 48000
            self._blocksize = 960
            self._stream = None
            self._pts = 0
            self._time_base = Fraction(1, self._samplerate)
            return

        import sounddevice as sd

        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._timeout_s = timeout_s
        self._samplerate = 48000
        self._blocksize = 960
        self._stream = None
        self._pts = 0
        self._time_base = Fraction(1, self._samplerate)

        def callback(indata, frames, time, status) -> None:
            self._queue.put_nowait(bytes(indata))

        try:
            self._stream = sd.RawInputStream(
                samplerate=self._samplerate,
                blocksize=self._blocksize,
                dtype="int16",
                channels=1,
                callback=callback,
            )
            self._stream.start()
        except Exception:
            self._stream = None

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
        frame.pts = self._pts
        frame.time_base = self._time_base
        self._pts += frame.samples
        return frame


def serialize_audio_frame(frame: AudioFrame) -> bytes:
    """Serialize an audio frame into a simple binary packet."""
    payload = bytes(frame.planes[0])
    header = struct.pack("<II", frame.sample_rate or 0, frame.samples)
    return header + payload


def deserialize_audio_packet(packet: bytes) -> AudioFrame:
    """Deserialize a binary audio packet into an AudioFrame."""
    if len(packet) < 8:
        raise ValueError("Audio packet too short.")
    samplerate, samples = struct.unpack("<II", packet[:8])
    payload = packet[8:]
    expected_bytes = samples * 2
    if len(payload) != expected_bytes:
        raise ValueError("Audio payload size mismatch.")
    frame = AudioFrame(format="s16", layout="mono", samples=samples)
    frame.planes[0].update(payload)
    frame.sample_rate = samplerate
    return frame
