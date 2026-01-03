"""WebRTC client lifecycle management."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import TcpSocketSignaling

from remote_client.control.handlers import ControlHandler
from remote_client.files.file_service import FileService, FileServiceError


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
        done_event = asyncio.Event()

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                done_event.set()

        @pc.on("datachannel")
        def on_datachannel(channel):
            @channel.on("message")
            async def on_message(message):
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError as exc:
                    self._send_error(channel, "invalid_json", str(exc))
                    return
                await self._handle_message(channel, payload)

        try:
            await self._signaling.connect()
            offer = await self._signaling.receive()
            if offer is None:
                return
            await pc.setRemoteDescription(offer)

            offered_kinds = {transceiver.kind for transceiver in pc.getTransceivers()}
            for track in self._media_tracks:
                if track.kind in offered_kinds:
                    pc.addTrack(track)

            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self._signaling.send(pc.localDescription)

            try:
                await asyncio.wait_for(done_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
        except (ConnectionError, OSError, asyncio.CancelledError):
            return
        finally:
            await pc.close()
            await self._signaling.close()

    async def _handle_message(self, channel, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        if not action:
            self._send_error(channel, "missing_action", "Message missing 'action'.")
            return
        if action == "control":
            try:
                self._control_handler.handle(payload)
            except (KeyError, ValueError, TypeError) as exc:
                self._send_error(channel, "invalid_control", str(exc))
            return

        if action == "list_files":
            path = payload.get("path", ".")
            try:
                entries = self._file_service.list_files(path)
            except FileServiceError as exc:
                self._send_error(channel, exc.code, str(exc))
                return
            channel.send(
                json.dumps({"files": self._file_service.serialize_entries(entries)})
            )
            return

        if action == "download":
            try:
                path = payload["path"]
            except KeyError as exc:
                self._send_error(channel, "missing_path", "Download missing 'path'.")
                return
            try:
                channel.send(self._file_service.read_file_base64(path))
            except FileServiceError as exc:
                self._send_error(channel, exc.code, str(exc))
            return

        self._send_error(channel, "unknown_action", f"Unknown action '{action}'.")

    @staticmethod
    def _send_error(channel, code: str, message: str) -> None:
        channel.send(json.dumps({"error": {"code": code, "message": message}}))
