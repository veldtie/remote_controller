import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import signaling_config as config
import signaling_db
import signaling_registry


router = APIRouter()
logger = logging.getLogger("signaling_server")
registry = signaling_registry.registry

cleanup_task: asyncio.Task | None = None
connected_time_task: asyncio.Task | None = None


def _extract_display_name(client_config: dict | None) -> str | None:
    if not client_config:
        return None
    for key in ("pc_name", "pc", "device_name", "device"):
        value = client_config.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _client_label(websocket: WebSocket) -> str:
    """Format a client label for logging."""
    if websocket.client:
        return f"{websocket.client.host}:{websocket.client.port}"
    return "unknown"


async def _close_websocket(websocket: WebSocket, code: int, reason: str) -> None:
    """Close a websocket, logging any failure."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        logger.exception("Failed to close websocket")


async def _cleanup_inactive_sessions() -> None:
    """Background task that closes idle sessions."""
    if config.SESSION_IDLE_TIMEOUT <= 0:
        return
    while True:
        await asyncio.sleep(max(1.0, config.SESSION_CLEANUP_INTERVAL))
        inactive = await registry.pop_inactive_sessions(config.SESSION_IDLE_TIMEOUT)
        for session_id, session in inactive:
            logger.warning("Session %s idle timeout exceeded, closing connections", session_id)
            if session.client is not None and session.device_token:
                await signaling_db.update_device_status(
                    session.device_token,
                    config.DEVICE_STATUS_DISCONNECTED,
                )
            await signaling_db.upsert_remote_client(session_id, "disconnected")
            for browser_ws in session.browsers.values():
                await _close_websocket(browser_ws, code=1001, reason="Idle timeout")
            if session.client is not None:
                await _close_websocket(session.client, code=1001, reason="Idle timeout")


async def start_background_tasks() -> None:
    """Start cleanup and connected time tasks."""
    global cleanup_task, connected_time_task
    await signaling_db.init_db()
    cleanup_task = asyncio.create_task(_cleanup_inactive_sessions())
    connected_time_task = asyncio.create_task(signaling_db.update_connected_time())


async def stop_background_tasks() -> None:
    """Stop cleanup tasks and close the database pool."""
    global cleanup_task, connected_time_task
    if cleanup_task:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
    if connected_time_task:
        connected_time_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await connected_time_task
    await signaling_db.close_db()


@router.websocket("/ws")
async def websocket_signaling(websocket: WebSocket) -> None:
    """WebSocket endpoint for signaling between browser and client."""
    session_id = websocket.query_params.get("session_id")
    role = websocket.query_params.get("role")
    operator_id = websocket.query_params.get("operator_id") if role == "browser" else None
    if config.SIGNALING_TOKEN:
        provided_token = websocket.query_params.get("token") or websocket.headers.get("x-rc-token")
        if not config.is_valid_signaling_token(provided_token):
            logger.warning("Rejected connection with invalid token from %s", _client_label(websocket))
            await websocket.close(code=1008)
            return
    if not session_id or role not in {"browser", "client"}:
        logger.warning(
            "Rejected connection with invalid params session_id=%s role=%s from %s",
            session_id,
            role,
            _client_label(websocket),
        )
        await websocket.close(code=1008)
        return
    await websocket.accept()
    replaced_browser = await registry.register(session_id, role, websocket, operator_id=operator_id)
    if replaced_browser and replaced_browser is not websocket:
        await _close_websocket(replaced_browser, code=1000, reason="Replaced by new connection")
    if role == "browser" and operator_id:
        logger.info(
            "Connected %s for session %s (operator %s) from %s",
            role,
            session_id,
            operator_id,
            _client_label(websocket),
        )
    else:
        logger.info("Connected %s for session %s from %s", role, session_id, _client_label(websocket))
    if role == "client":
        pending_messages = await registry.pop_pending_for_client(session_id)
        for queued in pending_messages:
            try:
                await websocket.send_text(queued)
            except Exception:
                logger.exception(
                    "Failed to flush pending signaling messages to client for session %s",
                    session_id,
                )
                break
    try:
        while True:
            message = await websocket.receive_text()
            target_session_id = session_id
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                payload = None
            operator_id = None
            message_type = None
            if isinstance(payload, dict):
                message_type = payload.get("type")
                operator_id = payload.get("operator_id")
                if role == "browser" and not operator_id:
                    operator_id = await registry.get_operator_id(websocket)
                    if operator_id:
                        payload["operator_id"] = operator_id
                        message = json.dumps(payload)
                if message_type in config.KEEPALIVE_MESSAGE_TYPES:
                    await registry.touch(session_id)
                    if role == "client":
                        _, _, device_token = await registry.get_session_state(session_id)
                        if device_token:
                            await signaling_db.touch_device_last_seen(device_token)
                    if message_type == "ping":
                        with contextlib.suppress(Exception):
                            await websocket.send_text(json.dumps({"type": "pong"}))
                    continue
                if message_type == "register":
                    if role == "client":
                        device_token = payload.get("device_token")
                        device_session_id = payload.get("session_id") or session_id
                        client_ip = config.resolve_client_ip(websocket.headers, websocket.client)
                        team_id = payload.get("team_id") or payload.get("team")
                        assigned_operator_id = payload.get("assigned_operator_id")
                        client_config = payload.get("client_config")
                        if client_config is not None and not isinstance(client_config, dict):
                            client_config = None
                        display_name = _extract_display_name(client_config)
                        if device_token:
                            has_browser, _ = await registry.set_device_token(
                                session_id, device_token
                            )
                            status = (
                                config.DEVICE_STATUS_ACTIVE
                                if has_browser
                                else config.DEVICE_STATUS_INACTIVE
                            )
                            await signaling_db.upsert_device(
                                device_token,
                                device_session_id,
                                client_ip,
                                status,
                            )
                        await signaling_db.upsert_remote_client(
                            device_session_id,
                            "connected",
                            client_ip,
                            team_id,
                            assigned_operator_id,
                            client_config,
                            display_name,
                        )
                    elif role == "browser":
                        _, has_client, device_token = await registry.get_session_state(
                            session_id
                        )
                        if device_token and has_client:
                            await signaling_db.update_device_status(
                                device_token, config.DEVICE_STATUS_ACTIVE
                            )
                if message_type == "ice":
                    target_session_id = payload.get("session_id") or session_id
            await registry.touch(session_id)
            if role == "client":
                _, _, device_token = await registry.get_session_state(session_id)
                if device_token:
                    await signaling_db.touch_device_last_seen(device_token)
            if target_session_id != session_id:
                await registry.touch(target_session_id)
            forwarded = await registry.forward(
                target_session_id, role, message, operator_id=operator_id
            )
            if (
                not forwarded
                and role == "browser"
                and message_type in {"offer", "ice"}
            ):
                await registry.queue_for_client(target_session_id, message, message_type)
    except WebSocketDisconnect:
        logger.info("Disconnected %s for session %s from %s", role, session_id, _client_label(websocket))
    except Exception:
        logger.exception("WebSocket error for session %s (%s)", session_id, role)
    finally:
        if role == "client":
            _, _, device_token = await registry.get_session_state(session_id)
            if device_token:
                await signaling_db.update_device_status(device_token, config.DEVICE_STATUS_DISCONNECTED)
            await signaling_db.upsert_remote_client(session_id, "disconnected")
        await registry.unregister(session_id, role, websocket)
        if role == "browser":
            has_browser, has_client, device_token = await registry.get_session_state(session_id)
            if device_token and has_client and not has_browser:
                await signaling_db.update_device_status(device_token, config.DEVICE_STATUS_INACTIVE)
