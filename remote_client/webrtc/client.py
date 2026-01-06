"""WebRTC client lifecycle management."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import logging
from typing import Any

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer,
)
from aiortc.sdp import candidate_from_sdp

from remote_client.control.handlers import ControlHandler
from remote_client.files.file_service import FileService, FileServiceError
from remote_client.webrtc.signaling import WebSocketSignaling

logger = logging.getLogger(__name__)


def _normalize_ice_servers(value: Any) -> list[dict[str, Any]]:
    """Normalize ICE server entries into a list of RTC-compatible dicts."""
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
    """Load ICE server config from the RC_ICE_SERVERS env var."""
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
        """Reconnect in a loop, keeping the client available."""
        while True:
            await self._run_once()
            await asyncio.sleep(2)

    async def _run_once(self) -> None:
        """Run a single signaling and WebRTC session."""
        peer_connection = RTCPeerConnection(self._rtc_configuration)
        connection_done = asyncio.Event()

        @peer_connection.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            if peer_connection.connectionState in {"failed", "closed", "disconnected"}:
                connection_done.set()

        @peer_connection.on("datachannel")
        def on_datachannel(data_channel):
            @data_channel.on("message")
            async def on_message(message):
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError as exc:
                    self._send_error(data_channel, "invalid_json", str(exc))
                    return
                await self._handle_message(data_channel, payload)

        @peer_connection.on("icecandidate")
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
            await peer_connection.setRemoteDescription(offer)

            offered_kinds = {
                transceiver.kind for transceiver in peer_connection.getTransceivers()
            }
            for track in self._media_tracks:
                if track.kind in offered_kinds:
                    peer_connection.addTrack(track)

            answer = await peer_connection.createAnswer()
            await peer_connection.setLocalDescription(answer)
            await self._signaling.send(
                {
                    "type": peer_connection.localDescription.type,
                    "sdp": peer_connection.localDescription.sdp,
                }
            )

            signaling_task = asyncio.create_task(self._signaling_loop(peer_connection))
            await connection_done.wait()
            signaling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await signaling_task
        except (ConnectionError, OSError, asyncio.CancelledError):
            return
        finally:
            await peer_connection.close()
            await self._signaling.close()

    async def _await_offer(self) -> dict[str, Any] | None:
        """Wait for an SDP offer from the signaling server."""
        while True:
            signaling_message = await self._signaling.receive()
            if signaling_message is None:
                return None
            if signaling_message.get("type") == "offer":
                return signaling_message

    async def _signaling_loop(self, peer_connection: RTCPeerConnection) -> None:
        """Relay ICE candidates from signaling to the peer connection."""
        while True:
            message = await self._signaling.receive()
            if message is None:
                return
            message_type = message.get("type")
            if message_type == "ice":
                candidate = message.get("candidate")
                if not candidate:
                    continue
                try:
                    candidate_sdp = candidate
                    if candidate_sdp.startswith("candidate:"):
                        candidate_sdp = candidate_sdp[len("candidate:") :]
                    ice_candidate = candidate_from_sdp(candidate_sdp)
                    ice_candidate.sdpMid = message.get("sdpMid")
                    ice_candidate.sdpMLineIndex = message.get("sdpMLineIndex")
                    await peer_connection.addIceCandidate(ice_candidate)
                except Exception as exc:
                    logger.warning("Failed to apply ICE candidate: %s", exc)

    async def _handle_message(self, data_channel, payload: dict[str, Any]) -> None:
        """Dispatch data channel actions."""
        action = payload.get("action")
        if not action:
            self._send_error(data_channel, "missing_action", "Message missing 'action'.")
            return
        if action == "control":
            try:
                self._control_handler.handle(payload)
            except (KeyError, ValueError, TypeError) as exc:
                self._send_error(data_channel, "invalid_control", str(exc))
            return

        if action == "list_files":
            path = payload.get("path", ".")
            try:
                entries = self._file_service.list_files(path)
            except FileServiceError as exc:
                self._send_error(data_channel, exc.code, str(exc))
                return
            data_channel.send(
                json.dumps({"files": self._file_service.serialize_entries(entries)})
            )
            return

        if action == "download":
            try:
                path = payload["path"]
            except KeyError as exc:
                self._send_error(data_channel, "missing_path", "Download missing 'path'.")
                return
            try:
                data_channel.send(self._file_service.read_file_base64(path))
            except FileServiceError as exc:
                self._send_error(data_channel, exc.code, str(exc))
            return

        self._send_error(
            data_channel, "unknown_action", f"Unknown action '{action}'."
        )

    @staticmethod
    def _send_error(data_channel, code: str, message: str) -> None:
        """Send a structured error over the data channel."""
        data_channel.send(json.dumps({"error": {"code": code, "message": message}}))
