# signaling_server.py
# WebRTC signaling server for Remote Desktop

import asyncio
import os
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

SIGNALING_HOST = os.getenv("RC_SIGNALING_HOST", "0.0.0.0")
SIGNALING_PORT = int(os.getenv("RC_SIGNALING_PORT", "8000"))
SIGNALING_TOKEN = os.getenv("RC_SIGNALING_TOKEN")

# Allow browser clients opened from file:// or other origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class SessionPair:
    browser: WebSocket | None = None
    client: WebSocket | None = None


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionPair] = {}
        self._client_by_session: dict[str, WebSocket] = {}
        self._session_by_client: dict[WebSocket, str] = {}
        self._browser_by_session: dict[str, WebSocket] = {}
        self._session_by_browser: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, role: str, websocket: WebSocket) -> None:
        async with self._lock:
            session = self._sessions.setdefault(session_id, SessionPair())
            if role == "browser":
                session.browser = websocket
                self._browser_by_session[session_id] = websocket
                self._session_by_browser[websocket] = session_id
            elif role == "client":
                session.client = websocket
                self._client_by_session[session_id] = websocket
                self._session_by_client[websocket] = session_id

    async def unregister(self, session_id: str, role: str, websocket: WebSocket) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            if role == "browser" and session.browser is websocket:
                session.browser = None
                self._browser_by_session.pop(session_id, None)
                self._session_by_browser.pop(websocket, None)
            if role == "client" and session.client is websocket:
                session.client = None
                self._client_by_session.pop(session_id, None)
                self._session_by_client.pop(websocket, None)
            if session.browser is None and session.client is None:
                self._sessions.pop(session_id, None)

    async def forward(self, session_id: str, role: str, message: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            peer = session.client if role == "browser" else session.browser
        if peer is not None:
            await peer.send_text(message)


registry = SessionRegistry()


@app.websocket("/ws")
async def websocket_signaling(websocket: WebSocket) -> None:
    session_id = websocket.query_params.get("session_id")
    role = websocket.query_params.get("role")
    if SIGNALING_TOKEN:
        provided_token = websocket.query_params.get("token") or websocket.headers.get("x-rc-token")
        if not provided_token or provided_token != SIGNALING_TOKEN:
            await websocket.close(code=1008)
            return
    if not session_id or role not in {"browser", "client"}:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await registry.register(session_id, role, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            await registry.forward(session_id, role, message)
    except WebSocketDisconnect:
        pass
    finally:
        await registry.unregister(session_id, role, websocket)


if __name__ == "__main__":
    uvicorn.run(app, host=SIGNALING_HOST, port=SIGNALING_PORT)
