"""Signaling helpers for the WebRTC client."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import websockets
from websockets import WebSocketClientProtocol


@dataclass
class WebSocketSignaling:
    url: str
    headers: dict[str, str] | None = None
    _socket: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._socket = await websockets.connect(
            self.url,
            additional_headers=self.headers,
        )

    async def receive(self) -> dict[str, Any] | None:
        if not self._socket:
            return None
        message = await self._socket.recv()
        if message is None:
            return None
        return json.loads(message)

    async def send(self, payload: dict[str, Any]) -> None:
        if not self._socket:
            return
        await self._socket.send(json.dumps(payload))

    async def close(self) -> None:
        if self._socket:
            await self._socket.close()
            self._socket = None


def _build_ws_url(base_url: str, query_params: dict[str, str]) -> str:
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
