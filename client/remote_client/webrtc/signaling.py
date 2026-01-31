"""Signaling helpers for the WebRTC client."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import websockets
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError


@dataclass
class WebSocketSignaling:
    """Thin wrapper around a WebSocket signaling channel."""
    url: str
    headers: dict[str, str] | None = None
    fallback_url: str | None = None
    _websocket: Any = None  # тип Any, чтобы избежать warning'ов; можно позже import ClientConnection

    async def connect(self) -> None:
        """Open the websocket connection with keep-alive."""
        connect_kwargs: dict[str, object] = {
            "ping_interval": 20,   # Отправляем ping каждые 20 секунд
            "ping_timeout": 60,    # Ждём pong до 60 секунд
            "close_timeout": 10,   # Таймаут на graceful close
        }

        if self.headers:
            connect_params = inspect.signature(websockets.connect).parameters
            if "additional_headers" in connect_params:
                connect_kwargs["additional_headers"] = self.headers
            elif "extra_headers" in connect_params:
                connect_kwargs["extra_headers"] = self.headers

        last_error: Exception | None = None
        for attempt_url in (self.url, self.fallback_url):
            if not attempt_url:
                continue
            try:
                print(f"[Signaling] Connecting to {attempt_url}")
                self._websocket = await websockets.connect(attempt_url, **connect_kwargs)
                self.url = attempt_url
                print("[Signaling] Connected successfully")
                return
            except Exception as exc:
                last_error = exc
                print(f"[Signaling] Connection failed for {attempt_url}: {exc}")
                self._websocket = None
        if last_error:
            raise last_error

    async def receive(self) -> dict[str, Any] | None:
        """Receive a JSON message from signaling with graceful handling of closure."""
        if not self._websocket:
            return None

        try:
            incoming_message = await self._websocket.recv()
            if incoming_message is None:
                return None
            return json.loads(incoming_message)
        except ConnectionClosedOK as e:
            print(f"[Signaling] Connection closed normally: code={e.code} reason='{e.reason}'")
            # Idle timeout (1001) или going away — не ошибка, просто возвращаем None
            return None
        except ConnectionClosedError as e:
            print(f"[Signaling] Connection closed unexpectedly: code={e.code} reason='{e.reason}'")
            # Можно добавить reconnect логику выше по стеку
            return None
        except Exception as e:
            print(f"[Signaling] Unexpected error during recv: {e}")
            return None

    async def send(self, payload: dict[str, Any]) -> None:
        """Send a JSON message over signaling."""
        if not self._websocket:
            return
        try:
            await self._websocket.send(json.dumps(payload))
        except Exception as e:
            print(f"[Signaling] Failed to send payload: {e}")

    async def close(self) -> None:
        """Close the websocket connection."""
        if self._websocket:
            print("[Signaling] Closing connection...")
            await self._websocket.close()
            self._websocket = None


def _build_ws_urls(base_url: str, query_params: dict[str, str]) -> tuple[str, str | None]:
    """Build websocket URLs from a base URL and query params."""
    parsed = urlparse(base_url)
    scheme = parsed.scheme
    if scheme in {"http", "https"}:
        scheme = "wss" if scheme == "https" else "ws"
    elif scheme not in {"ws", "wss"}:
        raise ValueError(f"Unsupported signaling URL scheme: {parsed.scheme}")

    existing_query = dict(parse_qsl(parsed.query))
    existing_query.update(query_params)

    path = parsed.path or "/ws"
    if not path.endswith("/ws"):
        path = path.rstrip("/") + "/ws"
    primary = urlunparse(
        parsed._replace(
            scheme=scheme,
            path=path,
            query=urlencode(existing_query),
        )
    )

    fallback = None
    if path != "/ws":
        fallback = urlunparse(
            parsed._replace(
                scheme=scheme,
                path="/ws",
                query=urlencode(existing_query),
            )
        )
        if fallback == primary:
            fallback = None
    return primary, fallback


def create_signaling(
    host: str,
    port: int,
    session_id: str,
    token: str | None = None,
    signaling_url: str | None = None,
) -> WebSocketSignaling:
    """Create signaling connection info from host/port settings."""
    query_params = {"session_id": session_id, "role": "client"}
    headers = None
    if token:
        query_params["token"] = token
        headers = {"x-rc-token": token}
    if signaling_url:
        url, fallback_url = _build_ws_urls(signaling_url, query_params)
    else:
        query = urlencode(query_params)
        url = f"ws://{host}:{port}/ws?{query}"
        fallback_url = None
    return WebSocketSignaling(url, headers=headers, fallback_url=fallback_url)

"""MAKS GAY"""
def create_signaling_from_url(
    base_url: str,
    session_id: str,
    token: str | None = None,
) -> WebSocketSignaling:
    """Create signaling connection info from a base URL."""
    query_params = dict(parse_qsl(urlparse(base_url).query))
    query_params.update({"session_id": session_id, "role": "client"})
    headers = None
    if token:
        query_params["token"] = token
        headers = {"x-rc-token": token}
    url, fallback_url = _build_ws_urls(base_url, query_params)
    return WebSocketSignaling(url, headers=headers, fallback_url=fallback_url)
