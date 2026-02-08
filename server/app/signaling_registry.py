import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger("signaling_server")


@dataclass
class SessionPair:
    """Active WebSocket pair for a single session."""
    browsers: dict[str, WebSocket] = field(default_factory=dict)
    client: WebSocket | None = None
    device_token: str | None = None
    pending_to_client: list[str] = field(default_factory=list)


class SessionRegistry:
    """Tracks active sessions and forwards signaling messages."""

    _pending_limit = 64

    def __init__(self) -> None:
        self._sessions: dict[str, SessionPair] = {}
        self._client_by_session: dict[str, WebSocket] = {}
        self._session_by_client: dict[WebSocket, str] = {}
        self._session_by_browser: dict[WebSocket, str] = {}
        self._browser_id_by_socket: dict[WebSocket, str] = {}
        self._last_activity: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        session_id: str,
        role: str,
        websocket: WebSocket,
        operator_id: str | None = None,
    ) -> WebSocket | None:
        """Register a websocket for the given role in a session."""
        replaced_browser: WebSocket | None = None
        async with self._lock:
            session_pair = self._sessions.setdefault(session_id, SessionPair())
            if role == "browser":
                if not operator_id:
                    operator_id = secrets.token_hex(8)
                replaced_browser = session_pair.browsers.get(operator_id)
                if replaced_browser and replaced_browser is not websocket:
                    self._session_by_browser.pop(replaced_browser, None)
                    self._browser_id_by_socket.pop(replaced_browser, None)
                session_pair.browsers[operator_id] = websocket
                self._session_by_browser[websocket] = session_id
                self._browser_id_by_socket[websocket] = operator_id
            elif role == "client":
                session_pair.client = websocket
                self._client_by_session[session_id] = websocket
                self._session_by_client[websocket] = session_id
            self._last_activity[session_id] = time.monotonic()
        return replaced_browser

    async def unregister(self, session_id: str, role: str, websocket: WebSocket) -> None:
        """Remove a websocket from session tracking."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return
            if role == "browser":
                operator_id = self._browser_id_by_socket.pop(websocket, None)
                if operator_id and session_pair.browsers.get(operator_id) is websocket:
                    session_pair.browsers.pop(operator_id, None)
                self._session_by_browser.pop(websocket, None)
            if role == "client" and session_pair.client is websocket:
                session_pair.client = None
                session_pair.device_token = None
                self._client_by_session.pop(session_id, None)
                self._session_by_client.pop(websocket, None)
            if not session_pair.browsers and session_pair.client is None:
                self._sessions.pop(session_id, None)
                self._last_activity.pop(session_id, None)

    async def forward(
        self,
        session_id: str,
        role: str,
        message: str,
        operator_id: str | None = None,
    ) -> bool:
        """Forward signaling payloads to the opposite role in a session."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return False
            if role == "browser":
                peer = session_pair.client
            else:
                if operator_id:
                    peer = session_pair.browsers.get(operator_id)
                elif len(session_pair.browsers) == 1:
                    peer = next(iter(session_pair.browsers.values()))
                else:
                    peer = None
        if peer is not None:
            try:
                await peer.send_text(message)
                return True
            except Exception:
                logger.warning(
                    "Failed to forward signaling message for session %s", session_id, exc_info=True
                )
                peer_role = "client" if role == "browser" else "browser"
                try:
                    await self.unregister(session_id, peer_role, peer)
                except Exception:
                    logger.exception(
                        "Failed to unregister stale websocket for session %s", session_id
                    )
        return False

    async def queue_for_client(self, session_id: str, message: str, message_type: str | None) -> None:
        """Queue browser signaling messages until the client connects."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return
            if message_type == "offer":
                session_pair.pending_to_client.clear()
            session_pair.pending_to_client.append(message)
            if len(session_pair.pending_to_client) > self._pending_limit:
                session_pair.pending_to_client = session_pair.pending_to_client[-self._pending_limit :]

    async def pop_pending_for_client(self, session_id: str) -> list[str]:
        """Pop queued browser messages for a client that just connected."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair or not session_pair.pending_to_client:
                return []
            pending = list(session_pair.pending_to_client)
            session_pair.pending_to_client.clear()
            return pending

    async def touch(self, session_id: str) -> None:
        """Update last activity time for a session."""
        async with self._lock:
            if session_id in self._sessions:
                self._last_activity[session_id] = time.monotonic()

    async def set_device_token(self, session_id: str, device_token: str) -> tuple[bool, bool]:
        """Associate a device token with a session and return browser/client presence."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return False, False
            session_pair.device_token = device_token
            return bool(session_pair.browsers), session_pair.client is not None

    async def get_session_state(self, session_id: str) -> tuple[bool, bool, str | None]:
        """Return browser/client presence and device token for a session."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return False, False, None
            return (
                bool(session_pair.browsers),
                session_pair.client is not None,
                session_pair.device_token,
            )

    async def get_operator_id(self, websocket: WebSocket) -> str | None:
        """Return the operator id for a browser websocket."""
        async with self._lock:
            return self._browser_id_by_socket.get(websocket)

    async def pop_inactive_sessions(self, idle_timeout: float) -> list[tuple[str, SessionPair]]:
        """Remove and return sessions that have been idle past the timeout."""
        now = time.monotonic()
        inactive: list[tuple[str, SessionPair]] = []
        async with self._lock:
            for session_id, last_seen in list(self._last_activity.items()):
                if now - last_seen <= idle_timeout:
                    continue
                session = self._sessions.pop(session_id, None)
                if not session:
                    self._last_activity.pop(session_id, None)
                    continue
                if session.browsers:
                    for browser_ws in list(session.browsers.values()):
                        self._session_by_browser.pop(browser_ws, None)
                        self._browser_id_by_socket.pop(browser_ws, None)
                if session.client is not None:
                    self._client_by_session.pop(session_id, None)
                    self._session_by_client.pop(session.client, None)
                self._last_activity.pop(session_id, None)
                inactive.append((session_id, session))
        return inactive


registry = SessionRegistry()
