"""Signaling helpers for the WebRTC client."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import websockets
from websockets import WebSocketClientProtocol


@dataclass
class WebSocketSignaling:
    """Thin wrapper around a WebSocket signaling channel."""
    url: str
    headers: dict[str, str] | None = None
    _websocket: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        """Open the websocket connection."""
        connect_kwargs: dict[str, object] = {}
        if self.headers:
            connect_params = inspect.signature(websockets.connect).parameters
            if "additional_headers" in connect_params:
                connect_kwargs["additional_headers"] = self.headers
            elif "extra_headers" in connect_params:
                connect_kwargs["extra_headers"] = self.headers
        self._websocket = await websockets.connect(self.url, **connect_kwargs)

    async def receive(self) -> dict[str, Any] | None:
        """Receive a JSON message from signaling."""
        if not self._websocket:
            return None
        incoming_message = await self._websocket.recv()
        if incoming_message is None:
            return None
        return json.loads(incoming_message)

    async def send(self, payload: dict[str, Any]) -> None:
        """Send a JSON message over signaling."""
        if not self._websocket:
            return
        await self._websocket.send(json.dumps(payload))

    async def close(self) -> None:
        """Close the websocket connection."""
        if self._websocket:
            await self._websocket.close()
            self._websocket = None


def _build_ws_url(base_url: str, query_params: dict[str, str]) -> str:
    """Build a websocket URL from a base URL and query params."""
    parsed = urlparse(base_url)
    scheme = parsed.scheme
    if scheme in {"http", "https"}:
        scheme = "wss" if scheme == "https" else "ws"
    elif scheme not in {"ws", "wss"}:
        raise ValueError(f"Unsupported signaling URL scheme: {parsed.scheme}")

    path = parsed.path or "/ws"
    existing_query = dict(parse_qsl(parsed.query))
    existing_query.update(query_params)
    return urlunparse(
        parsed._replace(
            scheme=scheme,
            path=path,
            query=urlencode(existing_query),
        )
    )


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
        url = _build_ws_url(signaling_url, query_params)
    else:
        query = urlencode(query_params)
        url = f"ws://{host}:{port}/ws?{query}"
    return WebSocketSignaling(url, headers=headers)


def create_signaling_from_url(
    base_url: str,
    session_id: str,
    token: str | None = None,
) -> WebSocketSignaling:
    """Create signaling connection info from a base URL."""
    parsed = urlparse(base_url)
    if parsed.scheme in {"http", "https"}:
        scheme = "wss" if parsed.scheme == "https" else "ws"
    else:
        scheme = parsed.scheme or "ws"
    path = parsed.path or "/ws"
    if not path.endswith("/ws"):
        path = path.rstrip("/") + "/ws"
    query_params = dict(parse_qsl(parsed.query))
    query_params.update({"session_id": session_id, "role": "client"})
    headers = None
    if token:
        query_params["token"] = token
        headers = {"x-rc-token": token}
    query = urlencode(query_params)
    url = urlunparse(parsed._replace(scheme=scheme, path=path, query=query))
    return WebSocketSignaling(url, headers=headers)
