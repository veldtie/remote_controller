"""WebRTC client lifecycle management."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from typing import Any

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    RTCConfiguration,
    RTCIceServer,
)

from remote_client.control.handlers import ControlHandler
from remote_client.files.file_service import FileService, FileServiceError
from remote_client.webrtc.signaling import WebSocketSignaling


def _normalize_ice_servers(value: Any) -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return servers
    for entry in value:
        if isinstance(entry, str):
            servers.append({"urls": [entry]})
            continue
        if not isinstance(entry, dict):
            continue
        urls = entry.get("urls") or entry.get("url")
        if not urls:
            continue
        if isinstance(urls, str):
            urls_list = [urls]
        elif isinstance(urls, list):
            urls_list = [item for item in urls if isinstance(item, str)]
        else:
            continue
        server: dict[str, Any] = {"urls": urls_list}
        if "username" in entry:
            server["username"] = entry["username"]
        if "credential" in entry:
            server["credential"] = entry["credential"]
        servers.append(server)
    return servers


def _load_ice_servers() -> list[RTCIceServer]:
    raw = os.getenv("RC_ICE_SERVERS")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    servers = _normalize_ice_servers(parsed)
    return [RTCIceServer(**server) for server in servers]


class WebRTCClient:
    """Manages WebRTC connections and dispatches data channel actions."""

    def __init__(
        self,
        session_id: str,
        signaling: WebSocketSignaling,
        control_handler: ControlHandler,
        file_service: FileService,
        media_tracks: list[Any],
    ) -> None:
        self._session_id = session_id
        self._signaling = signaling
        self._control_handler = control_handler
        self._file_service = file_service
        self._media_tracks = media_tracks
        self._rtc_configuration = RTCConfiguration(iceServers=_load_ice_servers())

    async def run_forever(self) -> None:
        while True:
            await self._run_once()
            await asyncio.sleep(2)

    async def _run_once(self) -> None:
        pc = RTCPeerConnection(self._rtc_configuration)
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

        @pc.on("icecandidate")
        async def on_icecandidate(candidate) -> None:
            if candidate is None:
                return
            await self._signaling.send(
                {
                    "type": "ice",
                    "session_id": self._session_id,
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                }
            )

        try:
            await self._signaling.connect()
            await self._signaling.send(
                {"type": "register", "session_id": self._session_id, "role": "client"}
            )
            offer_payload = await self._await_offer()
            if offer_payload is None:
                return
            offer = RTCSessionDescription(
                sdp=offer_payload["sdp"], type=offer_payload["type"]
            )
            await pc.setRemoteDescription(offer)

            offered_kinds = {transceiver.kind for transceiver in pc.getTransceivers()}
            for track in self._media_tracks:
                if track.kind in offered_kinds:
                    pc.addTrack(track)

            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self._signaling.send(
                {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
            )

            signaling_task = asyncio.create_task(self._signaling_loop(pc))
            try:
                await asyncio.wait_for(done_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
            finally:
                signaling_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await signaling_task
        except (ConnectionError, OSError, asyncio.CancelledError):
            return
        finally:
            await pc.close()
            await self._signaling.close()

    async def _await_offer(self) -> dict[str, Any] | None:
        while True:
            message = await self._signaling.receive()
            if message is None:
                return None
            if message.get("type") == "offer":
                return message

    async def _signaling_loop(self, pc: RTCPeerConnection) -> None:
        while True:
            message = await self._signaling.receive()
            if message is None:
                return
            message_type = message.get("type")
            if message_type == "ice":
                candidate = message.get("candidate")
                if not candidate:
                    continue
                await pc.addIceCandidate(
                    RTCIceCandidate(
                        candidate=candidate,
                        sdpMid=message.get("sdpMid"),
                        sdpMLineIndex=message.get("sdpMLineIndex"),
                    )
                )

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
