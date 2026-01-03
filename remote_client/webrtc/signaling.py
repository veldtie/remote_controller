"""Signaling helpers for the WebRTC client."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import websockets
from websockets import WebSocketClientProtocol


@dataclass
class WebSocketSignaling:
    url: str
    headers: dict[str, str] | None = None
    _socket: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._socket = await websockets.connect(self.url, extra_headers=self.headers)

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


def create_signaling(
    host: str,
    port: int,
    session_id: str,
    token: str | None = None,
) -> WebSocketSignaling:
    query_params = {"session_id": session_id, "role": "client"}
    headers = None
    if token:
        query_params["token"] = token
        headers = {"x-rc-token": token}
    query = urlencode(query_params)
    url = f"ws://{host}:{port}/ws?{query}"
    return WebSocketSignaling(url, headers=headers)
