import asyncio
from types import SimpleNamespace

import pytest

from remote_client.media.audio import AudioTrack


class DummyRawInputStream:
    def __init__(self, samplerate, blocksize, dtype, channels, callback) -> None:
        self.callback = callback
        self.started = False
        self.blocksize = blocksize

    def start(self) -> None:
        self.started = True

    def push(self, data: bytes) -> None:
        frames = len(data) // 2
        self.callback(data, frames, None, None)


@pytest.fixture
def mocked_sounddevice(monkeypatch) -> DummyRawInputStream:
    stream_holder: dict[str, DummyRawInputStream] = {}

    def _factory(*args, **kwargs):
        stream_holder["stream"] = DummyRawInputStream(*args, **kwargs)
        return stream_holder["stream"]

    monkeypatch.setitem(
        __import__("sys").modules,
        "sounddevice",
        SimpleNamespace(RawInputStream=_factory),
    )
    return stream_holder


def test_audio_stream_long_running_no_crash(mocked_sounddevice) -> None:
    async def _run() -> None:
        track = AudioTrack(timeout_s=0.01)
        stream = mocked_sounddevice["stream"]
        payload = b"\x01\x02" * track._blocksize

        for _ in range(50):
            stream.push(payload)
            frame = await track.recv()
            assert frame.sample_rate == track._samplerate
            assert frame.samples == track._blocksize

    asyncio.run(_run())


def test_audio_stream_timeout_returns_silence(mocked_sounddevice) -> None:
    async def _run() -> None:
        track = AudioTrack(timeout_s=0.001)
        frame = await track.recv()
        assert frame.sample_rate == track._samplerate
        assert frame.samples == track._blocksize
        assert frame.planes[0].to_bytes() == b"\x00" * (track._blocksize * 2)

    asyncio.run(_run())


def test_audio_stream_continuous_delivery_with_gaps(mocked_sounddevice) -> None:
    async def _run() -> None:
        track = AudioTrack(timeout_s=0.001)
        stream = mocked_sounddevice["stream"]
        payload = b"\x05\x00" * track._blocksize

        async def producer() -> None:
            for idx in range(20):
                if idx % 5 != 0:
                    stream.push(payload)
                await asyncio.sleep(0)

        producer_task = asyncio.create_task(producer())
        frames = [await track.recv() for _ in range(20)]
        await producer_task

        assert len(frames) == 20
        assert all(frame.sample_rate == track._samplerate for frame in frames)

    asyncio.run(_run())
