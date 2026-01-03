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
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, role: str, websocket: WebSocket) -> None:
        async with self._lock:
            session = self._sessions.setdefault(session_id, SessionPair())
            if role == "browser":
                session.browser = websocket
            elif role == "client":
                session.client = websocket

    async def unregister(self, session_id: str, role: str, websocket: WebSocket) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            if role == "browser" and session.browser is websocket:
                session.browser = None
            if role == "client" and session.client is websocket:
                session.client = None
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
