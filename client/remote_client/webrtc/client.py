"""WebRTC client lifecycle management."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import inspect
import json
import os
import logging
import secrets
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
from remote_client.proxy.store import get_proxy_settings
from remote_client.security.e2ee import E2EEContext, E2EEError
from remote_client.config import resolve_ice_servers
from remote_client.webrtc.signaling import WebSocketSignaling

logger = logging.getLogger(__name__)

def _read_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _read_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _resolve_bitrate_bps(env_value: str | None, default_bps: int) -> int:
    if env_value is None:
        return default_bps
    try:
        value = int(env_value)
    except (TypeError, ValueError):
        return default_bps
    if value <= 0:
        return 0
    if value < 1_000_000:
        return value * 1000
    return value


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_session_mode(mode: Any) -> str:
    if not mode:
        return "manage"
    value = str(mode).strip().lower()
    if value in {"view", "viewer", "readonly"}:
        return "view"
    if value in {"hidden", "hidden-manage", "hidden_manage", "hidden-desktop", "hidden_desktop"}:
        return "hidden"
    return "manage"


def _resolve_profile_bitrate(profile: str | None) -> int:
    if not profile:
        return VIDEO_MAX_BITRATE_BPS
    name = str(profile).strip().lower()
    if name == "reading":
        return VIDEO_MAX_BITRATE_READING_BPS
    return VIDEO_MAX_BITRATE_BPS


SIGNALING_PING_INTERVAL = max(0.0, _read_env_float("RC_SIGNALING_PING_INTERVAL", 20.0))
DISCONNECT_GRACE_SECONDS = max(0.0, _read_env_float("RC_DISCONNECT_GRACE", 30.0))
RECONNECT_BASE_DELAY = max(0.5, _read_env_float("RC_RECONNECT_DELAY", 2.0))
RECONNECT_MAX_DELAY = max(RECONNECT_BASE_DELAY, _read_env_float("RC_RECONNECT_MAX_DELAY", 30.0))
VIDEO_MAX_BITRATE_BPS = _resolve_bitrate_bps(
    os.getenv("RC_VIDEO_MAX_BITRATE"), 20_000_000
)
VIDEO_MAX_BITRATE_READING_BPS = _resolve_bitrate_bps(
    os.getenv("RC_VIDEO_MAX_BITRATE_READING"),
    max(VIDEO_MAX_BITRATE_BPS, 26_000_000),
)
VIDEO_MAX_FPS = max(0, _read_env_int("RC_VIDEO_MAX_FPS", 0))
DATA_CHUNK_SIZE = max(4096, _read_env_int("RC_DATA_CHUNK_SIZE", 48000))
DATA_CHANNEL_BUFFER_LIMIT = max(64_000, _read_env_int("RC_DATA_CHANNEL_BUFFER", 2_000_000))


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
    resolved = resolve_ice_servers()
    if resolved is not None:
        servers = _normalize_ice_servers(resolved)
        logger.info("Using %s ICE server(s) from config.", len(servers))
        return [RTCIceServer(**server) for server in servers]
    default_servers = [
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
        RTCIceServer(urls=["stun:stun.cloudflare.com:3478"]),
    ]
    logger.info("Using default public STUN servers.")
    return default_servers


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
    set_cursor_visibility: Callable[[bool], None] | None = None


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
        self._ice_servers = _load_ice_servers()
        self._force_host_only = False
        self._pending_offer: dict[str, Any] | None = None
        self._current_mode: str = "manage"
        self._video_sender = None

    def _build_rtc_configuration(self) -> RTCConfiguration:
        if self._force_host_only:
            return RTCConfiguration(iceServers=[])
        return RTCConfiguration(iceServers=self._ice_servers)

    async def run_forever(self) -> None:
        """Reconnect in a loop, keeping the client available."""
        delay = RECONNECT_BASE_DELAY
        while True:
            try:
                await self._run_once()
                delay = RECONNECT_BASE_DELAY
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Unexpected error in client loop: %s", exc)
                delay = min(RECONNECT_MAX_DELAY, max(delay * 2, RECONNECT_BASE_DELAY))
            await asyncio.sleep(delay)

    async def _signaling_keepalive(self) -> None:
        """Periodically send signaling keepalive messages to prevent idle timeouts."""
        if SIGNALING_PING_INTERVAL <= 0:
            return
        while True:
            await asyncio.sleep(SIGNALING_PING_INTERVAL)
            await self._signaling.send(
                {"type": "ping", "session_id": self._session_id, "role": "client"}
            )

    async def _tune_video_sender(
        self,
        sender,
        bitrate_bps: int | None = None,
        max_fps: int | None = None,
    ) -> None:
        """Apply video sender constraints to improve bitrate/quality when possible."""
        target_bitrate = VIDEO_MAX_BITRATE_BPS if bitrate_bps is None else bitrate_bps
        target_fps = VIDEO_MAX_FPS if max_fps is None else max_fps
        if sender is None or (target_bitrate <= 0 and target_fps <= 0):
            return
        try:
            params = sender.getParameters()
        except Exception as exc:
            logger.debug("Sender parameters unavailable: %s", exc)
            return
        encodings = getattr(params, "encodings", None)
        if not encodings:
            return
        encoding = encodings[0]
        if target_bitrate > 0:
            try:
                encoding.maxBitrate = target_bitrate
            except Exception:
                pass
        if target_fps > 0:
            try:
                encoding.maxFramerate = target_fps
            except Exception:
                pass
        try:
            result = sender.setParameters(params)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.debug("Failed to set sender parameters: %s", exc)

    async def _apply_sender_profile(self, profile: str | None) -> None:
        if not self._video_sender:
            return
        bitrate = _resolve_profile_bitrate(profile)
        await self._tune_video_sender(self._video_sender, bitrate_bps=bitrate)

    async def _run_once(self) -> None:
        """Run a single signaling and WebRTC session."""
        if self._force_host_only:
            logger.warning("Using host-only ICE (STUN/TURN disabled) for this session.")
        peer_connection = RTCPeerConnection(self._build_rtc_configuration())
        self._video_sender = None
        connection_done = asyncio.Event()
        disconnect_task: asyncio.Task | None = None
        keepalive_task: asyncio.Task | None = None
        control_handler: ControlHandler | None = None
        session_cleanup: Callable[[], None] | None = None
        session_actions: SessionResources | None = None
        operator_id_holder: dict[str, str | None] = {"value": None}
        had_connection = False
        pending_ice: list[dict[str, Any]] = []

        def _cancel_disconnect_task() -> None:
            nonlocal disconnect_task
            if disconnect_task and not disconnect_task.done():
                disconnect_task.cancel()
            disconnect_task = None

        async def _schedule_disconnect() -> None:
            nonlocal disconnect_task
            if not had_connection:
                return
            if DISCONNECT_GRACE_SECONDS <= 0:
                connection_done.set()
                return
            if disconnect_task and not disconnect_task.done():
                return

            async def _wait_for_disconnect() -> None:
                try:
                    await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
                except asyncio.CancelledError:
                    return
                if (
                    peer_connection.connectionState == "disconnected"
                    or peer_connection.iceConnectionState == "disconnected"
                ):
                    connection_done.set()

            disconnect_task = asyncio.create_task(_wait_for_disconnect())

        @peer_connection.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            nonlocal had_connection
            state = peer_connection.connectionState
            logger.info(
                "Connection state changed to %s (ice=%s signaling=%s).",
                state,
                peer_connection.iceConnectionState,
                peer_connection.signalingState,
            )
            if state in {"failed", "closed"}:
                connection_done.set()
                return
            if state == "disconnected":
                await _schedule_disconnect()
                return
            if state == "connected":
                had_connection = True
            _cancel_disconnect_task()

        @peer_connection.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange() -> None:
            nonlocal had_connection
            state = peer_connection.iceConnectionState
            logger.info("ICE connection state changed to %s.", state)
            if state in {"failed", "closed"}:
                if state == "failed" and not had_connection and not self._force_host_only:
                    logger.warning("ICE failed before connection; retrying with host-only ICE.")
                    self._force_host_only = True
                connection_done.set()
                return
            if state == "disconnected":
                await _schedule_disconnect()
                return
            if state in {"connected", "completed"}:
                had_connection = True
                _cancel_disconnect_task()

        @peer_connection.on("icegatheringstatechange")
        async def on_icegatheringstatechange() -> None:
            logger.info("ICE gathering state changed to %s.", peer_connection.iceGatheringState)

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
                logger.debug("ICE gathering completed.")
                return
            logger.debug(
                "Sending ICE candidate sdpMid=%s sdpMLineIndex=%s",
                candidate.sdpMid,
                candidate.sdpMLineIndex,
            )
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

        @peer_connection.on("signalingstatechange")
        async def on_signalingstatechange() -> None:
            logger.info("Signaling state changed to %s.", peer_connection.signalingState)

        async def _apply_ice_candidate(message: dict[str, Any]) -> None:
            message_operator = message.get("operator_id")
            if (
                operator_id_holder["value"]
                and message_operator
                and message_operator != operator_id_holder["value"]
            ):
                return
            if operator_id_holder["value"] is None and message_operator:
                operator_id_holder["value"] = message_operator
            candidate = message.get("candidate")
            if not candidate:
                return
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

        try:
            await self._signaling.connect()
            logger.info("Signaling connected.")
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
            keepalive_task = asyncio.create_task(self._signaling_keepalive())
            offer_payload = await self._await_offer(pending_ice)
            if offer_payload is None:
                return
            logger.info(
                "Received offer (has_sdp=%s operator_id=%s).",
                bool(offer_payload.get("sdp")),
                offer_payload.get("operator_id"),
            )
            operator_id_holder["value"] = offer_payload.get("operator_id")
            session_mode = _normalize_session_mode(offer_payload.get("mode"))
            self._current_mode = session_mode
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
            if pending_ice:
                for message in pending_ice:
                    await _apply_ice_candidate(message)
                pending_ice.clear()

            offered_kinds = {
                transceiver.kind for transceiver in peer_connection.getTransceivers()
            }
            for track in media_tracks:
                if track.kind in offered_kinds:
                    sender = peer_connection.addTrack(track)
                    if track.kind == "video":
                        self._video_sender = sender
                        await self._tune_video_sender(sender, bitrate_bps=_resolve_profile_bitrate(None))

            answer = await peer_connection.createAnswer()
            await peer_connection.setLocalDescription(answer)
            logger.info("Sending answer (has_sdp=%s).", bool(peer_connection.localDescription and peer_connection.localDescription.sdp))
            answer_payload = {
                "type": peer_connection.localDescription.type,
                "sdp": peer_connection.localDescription.sdp,
            }
            if operator_id_holder["value"]:
                answer_payload["operator_id"] = operator_id_holder["value"]
            await self._signaling.send(answer_payload)

            signaling_task = asyncio.create_task(
                self._signaling_loop(peer_connection, operator_id_holder, _apply_ice_candidate)
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
            if keepalive_task:
                keepalive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await keepalive_task
            if disconnect_task:
                disconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await disconnect_task
            await peer_connection.close()
            await self._signaling.close()
            if session_cleanup:
                try:
                    session_cleanup()
                except Exception as exc:
                    logger.warning("Session cleanup failed: %s", exc)

    async def _await_offer(self, pending_ice: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Wait for an SDP offer from the signaling server."""
        if self._pending_offer:
            offer = self._pending_offer
            self._pending_offer = None
            return offer
        while True:
            signaling_message = await self._signaling.receive()
            if signaling_message is None:
                return None
            message_type = signaling_message.get("type")
            if message_type:
                logger.debug("Signaling message received: %s", message_type)
            if message_type == "offer":
                return signaling_message
            if message_type == "ice" and signaling_message.get("candidate"):
                pending_ice.append(signaling_message)

    async def _signaling_loop(
        self,
        peer_connection: RTCPeerConnection,
        operator_id_holder: dict[str, str | None],
        apply_ice: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Relay ICE candidates from signaling to the peer connection."""
        while True:
            message = await self._signaling.receive()
            if message is None:
                return
            message_type = message.get("type")
            if message_type:
                logger.debug("Signaling message received: %s", message_type)
            if message_type == "offer":
                offer_mode = _normalize_session_mode(message.get("mode"))
                if peer_connection.connectionState in {"connecting", "connected"}:
                    if offer_mode == "view" and self._current_mode in {"manage", "hidden"}:
                        continue
                self._pending_offer = message
                return
            if message_type == "ice":
                await apply_ice(message)

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
            message_type = payload.get("type")
            if message_type in {"toggle_virtual_cursor", "cursor_visibility"}:
                visible = _parse_bool(payload.get("visible"), True)
                if session_actions and session_actions.set_cursor_visibility:
                    session_actions.set_cursor_visibility(visible)
                return
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
                payload_base64 = await asyncio.to_thread(exporter.export_base64, browsers)
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
            await self._send_chunked_payload(data_channel, payload_base64, "cookies")
            return

        if action == "export_proxy":
            settings = get_proxy_settings()
            if not settings:
                self._send_error(
                    data_channel,
                    "proxy_unavailable",
                    "Proxy settings are not configured.",
                )
                return
            payload_text = await asyncio.to_thread(settings.to_text)
            payload_base64 = base64.b64encode(payload_text.encode("utf-8")).decode("ascii")
            await self._send_chunked_payload(data_channel, payload_base64, "proxy")
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
                await self._apply_sender_profile(profile)
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

    async def _send_chunked_payload(self, data_channel, payload_base64: str, kind: str) -> None:
        """Send large base64 payloads over the data channel in chunks."""
        if not payload_base64:
            self._send_payload(data_channel, payload_base64)
            return
        if len(payload_base64) <= DATA_CHUNK_SIZE:
            self._send_payload(data_channel, payload_base64)
            return
        transfer_id = secrets.token_hex(8)
        total = (len(payload_base64) + DATA_CHUNK_SIZE - 1) // DATA_CHUNK_SIZE
        buffer_limit = DATA_CHANNEL_BUFFER_LIMIT
        drain_target = max(DATA_CHUNK_SIZE * 2, buffer_limit // 2)
        for index in range(total):
            start = index * DATA_CHUNK_SIZE
            end = start + DATA_CHUNK_SIZE
            chunk = payload_base64[start:end]
            self._send_payload(
                data_channel,
                {
                    "action": "download_chunk",
                    "kind": kind,
                    "transfer_id": transfer_id,
                    "index": index,
                    "total": total,
                    "data": chunk,
                },
            )
            await asyncio.sleep(0)
            await self._drain_data_channel(data_channel, buffer_limit, drain_target)

    async def _drain_data_channel(
        self,
        data_channel,
        buffer_limit: int,
        drain_target: int,
    ) -> None:
        """Throttle sends when the data channel buffer grows too large."""
        if not data_channel:
            return
        try:
            buffered = int(getattr(data_channel, "bufferedAmount", 0) or 0)
        except Exception:
            buffered = 0
        if buffered <= buffer_limit:
            return
        start = asyncio.get_event_loop().time()
        while buffered > drain_target:
            await asyncio.sleep(0.02)
            try:
                buffered = int(getattr(data_channel, "bufferedAmount", 0) or 0)
            except Exception:
                buffered = 0
                break
            if asyncio.get_event_loop().time() - start > 5.0:
                break

    def _send_error(self, data_channel, code: str, message: str) -> None:
        """Send a structured error over the data channel."""
        self._send_payload(data_channel, {"error": {"code": code, "message": message}})
