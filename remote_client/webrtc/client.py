"""WebRTC client lifecycle management."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import TcpSocketSignaling

from remote_client.control.handlers import ControlHandler
from remote_client.files.file_service import FileService


class WebRTCClient:
    """Manages WebRTC connections and dispatches data channel actions."""

    def __init__(
        self,
        signaling: TcpSocketSignaling,
        control_handler: ControlHandler,
        file_service: FileService,
        media_tracks: list[Any],
    ) -> None:
        self._signaling = signaling
        self._control_handler = control_handler
        self._file_service = file_service
        self._media_tracks = media_tracks

    async def run_forever(self) -> None:
        while True:
            await self._run_once()
            await asyncio.sleep(2)

    async def _run_once(self) -> None:
        pc = RTCPeerConnection()
        for track in self._media_tracks:
            pc.addTrack(track)

        @pc.on("datachannel")
        def on_datachannel(channel):
            @channel.on("message")
            async def on_message(message):
                payload = json.loads(message)
                await self._handle_message(channel, payload)

        try:
            await self._signaling.connect()
            offer = await self._signaling.receive()
            await pc.setRemoteDescription(offer)

            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self._signaling.send(pc.localDescription)

            while True:
                await asyncio.sleep(1)
        except (ConnectionError, OSError, asyncio.CancelledError):
            await pc.close()

    async def _handle_message(self, channel, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        if action == "control":
            self._control_handler.handle(payload)
            return

        if action == "list_files":
            path = payload.get("path", ".")
            entries = self._file_service.list_files(path)
            channel.send(json.dumps({"files": self._file_service.serialize_entries(entries)}))
            return

        if action == "download":
            channel.send(self._file_service.read_file_base64(payload["path"]))
            return
