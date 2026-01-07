# signaling_server.py
# WebRTC signaling server for Remote Desktop

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

import asyncpg
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

SIGNALING_HOST = os.getenv("RC_SIGNALING_HOST", "0.0.0.0")
SIGNALING_PORT = int(os.getenv("RC_SIGNALING_PORT", "8000"))
SIGNALING_TOKEN_FILE = os.getenv("RC_SIGNALING_TOKEN_FILE")
SESSION_IDLE_TIMEOUT = float(os.getenv("RC_SESSION_IDLE_TIMEOUT", "300"))
SESSION_CLEANUP_INTERVAL = float(os.getenv("RC_SESSION_CLEANUP_INTERVAL", "30"))
DATABASE_URL = os.getenv("RC_DATABASE_URL")
DB_POOL_MIN = int(os.getenv("RC_DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("RC_DB_POOL_MAX", "5"))
DB_CONNECT_RETRIES = int(os.getenv("RC_DB_CONNECT_RETRIES", "5"))
DB_STATEMENT_CACHE_SIZE = int(os.getenv("RC_DB_STATEMENT_CACHE_SIZE", "0"))
TRUST_PROXY = os.getenv("RC_TRUST_PROXY", "").lower() in {"1", "true", "yes", "on"}

logging.basicConfig(
    level=os.getenv("RC_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("signaling_server")
db_pool: asyncpg.Pool | None = None

DEVICE_STATUS_ACTIVE = "active"
DEVICE_STATUS_INACTIVE = "inactive"
DEVICE_STATUS_DISCONNECTED = "disconnected"


def _load_signaling_token() -> str | None:
    env_token = os.getenv("RC_SIGNALING_TOKEN")
    if env_token:
        return env_token.strip()
    if not SIGNALING_TOKEN_FILE:
        return None
    try:
        with open(SIGNALING_TOKEN_FILE, "r", encoding="utf-8") as handle:
            stored = handle.read().strip()
            if stored:
                return stored
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Failed to read signaling token file %s", SIGNALING_TOKEN_FILE)
    token = secrets.token_urlsafe(32)
    try:
        token_dir = os.path.dirname(SIGNALING_TOKEN_FILE)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        with open(SIGNALING_TOKEN_FILE, "w", encoding="utf-8") as handle:
            handle.write(token)
        logger.info("Generated new signaling token in %s", SIGNALING_TOKEN_FILE)
    except OSError:
        logger.warning("Failed to persist generated signaling token to %s", SIGNALING_TOKEN_FILE)
    return token


def _normalize_ice_servers(value) -> list[dict[str, object]]:
    """Normalize ICE server entries into a list of RTC-compatible dicts."""
    servers: list[dict[str, object]] = []
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
        server: dict[str, object] = {"urls": urls_list}
        if "username" in entry:
            server["username"] = entry["username"]
        if "credential" in entry:
            server["credential"] = entry["credential"]
        servers.append(server)
    return servers


def _load_ice_servers() -> list[dict[str, object]]:
    """Load ICE server config from the RC_ICE_SERVERS env var."""
    raw = os.getenv("RC_ICE_SERVERS")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return _normalize_ice_servers(parsed)


ICE_SERVERS = _load_ice_servers()
SIGNALING_TOKEN = _load_signaling_token()

DEVICE_REGISTRY_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS device_registry (
        device_token TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        external_ip TEXT,
        status TEXT NOT NULL DEFAULT 'inactive',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "ALTER TABLE device_registry ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'inactive';",
]


def _extract_forwarded_ip(headers) -> str | None:
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return None


def _resolve_client_ip(headers, client) -> str | None:
    if TRUST_PROXY:
        forwarded = _extract_forwarded_ip(headers)
        if forwarded:
            return forwarded
    if client:
        return client.host
    return None


async def _init_db() -> None:
    """Initialize the asyncpg pool and schema when configured."""
    global db_pool
    if not DATABASE_URL:
        logger.info("Database disabled (RC_DATABASE_URL not set).")
        return
    for attempt in range(1, DB_CONNECT_RETRIES + 1):
        try:
            db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=DB_POOL_MIN,
                max_size=DB_POOL_MAX,
                statement_cache_size=DB_STATEMENT_CACHE_SIZE,
            )
            async with db_pool.acquire() as conn:
                for statement in DEVICE_REGISTRY_SCHEMA:
                    await conn.execute(statement)
            logger.info("Database connection established.")
            return
        except Exception:
            logger.exception("Database connection failed (attempt %s).", attempt)
            await asyncio.sleep(min(5, attempt))
    raise RuntimeError("Database connection failed after retries.")


async def _close_db() -> None:
    """Close the database pool if initialized."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


async def _upsert_device(
    device_token: str,
    session_id: str,
    external_ip: str | None,
    status: str,
) -> None:
    """Insert or update a device registry record."""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO device_registry (device_token, session_id, external_ip, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (device_token)
                DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    external_ip = EXCLUDED.external_ip,
                    status = EXCLUDED.status,
                    last_seen = NOW();
                """,
                device_token,
                session_id,
                external_ip,
                status,
            )
    except Exception:
        logger.exception("Failed to upsert device record for token %s", device_token)


async def _update_device_status(device_token: str, status: str) -> None:
    """Update device status and last_seen for an existing record."""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE device_registry
                SET status = $2,
                    last_seen = NOW()
                WHERE device_token = $1;
                """,
                device_token,
                status,
            )
    except Exception:
        logger.exception("Failed to update status for token %s", device_token)

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
    """Active WebSocket pair for a single session."""
    browser: WebSocket | None = None
    client: WebSocket | None = None
    device_token: str | None = None


class SessionRegistry:
    """Tracks active sessions and forwards signaling messages."""
    def __init__(self) -> None:
        self._sessions: dict[str, SessionPair] = {}
        self._client_by_session: dict[str, WebSocket] = {}
        self._session_by_client: dict[WebSocket, str] = {}
        self._browser_by_session: dict[str, WebSocket] = {}
        self._session_by_browser: dict[WebSocket, str] = {}
        self._last_activity: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, role: str, websocket: WebSocket) -> None:
        """Register a websocket for the given role in a session."""
        async with self._lock:
            session_pair = self._sessions.setdefault(session_id, SessionPair())
            if role == "browser":
                session_pair.browser = websocket
                self._browser_by_session[session_id] = websocket
                self._session_by_browser[websocket] = session_id
            elif role == "client":
                session_pair.client = websocket
                self._client_by_session[session_id] = websocket
                self._session_by_client[websocket] = session_id
            self._last_activity[session_id] = time.monotonic()

    async def unregister(self, session_id: str, role: str, websocket: WebSocket) -> None:
        """Remove a websocket from session tracking."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return
            if role == "browser" and session_pair.browser is websocket:
                session_pair.browser = None
                self._browser_by_session.pop(session_id, None)
                self._session_by_browser.pop(websocket, None)
            if role == "client" and session_pair.client is websocket:
                session_pair.client = None
                session_pair.device_token = None
                self._client_by_session.pop(session_id, None)
                self._session_by_client.pop(websocket, None)
            if session_pair.browser is None and session_pair.client is None:
                self._sessions.pop(session_id, None)
                self._last_activity.pop(session_id, None)

    async def forward(self, session_id: str, role: str, message: str) -> None:
        """Forward signaling payloads to the opposite role in a session."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return
            peer = session_pair.client if role == "browser" else session_pair.browser
        if peer is not None:
            await peer.send_text(message)

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
            return session_pair.browser is not None, session_pair.client is not None

    async def get_session_state(self, session_id: str) -> tuple[bool, bool, str | None]:
        """Return browser/client presence and device token for a session."""
        async with self._lock:
            session_pair = self._sessions.get(session_id)
            if not session_pair:
                return False, False, None
            return (
                session_pair.browser is not None,
                session_pair.client is not None,
                session_pair.device_token,
            )

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
                if session.browser is not None:
                    self._browser_by_session.pop(session_id, None)
                    self._session_by_browser.pop(session.browser, None)
                if session.client is not None:
                    self._client_by_session.pop(session_id, None)
                    self._session_by_client.pop(session.client, None)
                self._last_activity.pop(session_id, None)
                inactive.append((session_id, session))
        return inactive


registry = SessionRegistry()
cleanup_task: asyncio.Task | None = None


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
    if SESSION_IDLE_TIMEOUT <= 0:
        return
    while True:
        await asyncio.sleep(max(1.0, SESSION_CLEANUP_INTERVAL))
        inactive = await registry.pop_inactive_sessions(SESSION_IDLE_TIMEOUT)
        for session_id, session in inactive:
            logger.warning("Session %s idle timeout exceeded, closing connections", session_id)
            if session.client is not None and session.device_token:
                await _update_device_status(session.device_token, DEVICE_STATUS_DISCONNECTED)
            if session.browser is not None:
                await _close_websocket(session.browser, code=1001, reason="Idle timeout")
            if session.client is not None:
                await _close_websocket(session.client, code=1001, reason="Idle timeout")


@app.on_event("startup")
async def _start_cleanup_task() -> None:
    """Start the idle session cleanup task."""
    global cleanup_task
    await _init_db()
    cleanup_task = asyncio.create_task(_cleanup_inactive_sessions())


@app.on_event("shutdown")
async def _stop_cleanup_task() -> None:
    """Stop the idle session cleanup task."""
    global cleanup_task
    if cleanup_task:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
    await _close_db()


@app.get("/ice-config")
async def ice_config(request: Request) -> dict[str, list[dict[str, object]]]:
    """Return ICE server configuration when a token is valid."""
    if SIGNALING_TOKEN:
        provided_token = request.query_params.get("token") or request.headers.get("x-rc-token")
        if not provided_token or provided_token != SIGNALING_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")
    return {"iceServers": ICE_SERVERS}


@app.websocket("/ws")
async def websocket_signaling(websocket: WebSocket) -> None:
    """WebSocket endpoint for signaling between browser and client."""
    session_id = websocket.query_params.get("session_id")
    role = websocket.query_params.get("role")
    if SIGNALING_TOKEN:
        provided_token = websocket.query_params.get("token") or websocket.headers.get("x-rc-token")
        if not provided_token or provided_token != SIGNALING_TOKEN:
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
    await registry.register(session_id, role, websocket)
    logger.info("Connected %s for session %s from %s", role, session_id, _client_label(websocket))
    try:
        while True:
            message = await websocket.receive_text()
            target_session_id = session_id
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                message_type = payload.get("type")
                if message_type == "register":
                    if role == "client":
                        device_token = payload.get("device_token")
                        if device_token:
                            device_session_id = payload.get("session_id") or session_id
                            client_ip = _resolve_client_ip(websocket.headers, websocket.client)
                            has_browser, _ = await registry.set_device_token(
                                session_id, device_token
                            )
                            status = (
                                DEVICE_STATUS_ACTIVE
                                if has_browser
                                else DEVICE_STATUS_INACTIVE
                            )
                            await _upsert_device(
                                device_token,
                                device_session_id,
                                client_ip,
                                status,
                            )
                    elif role == "browser":
                        _, has_client, device_token = await registry.get_session_state(
                            session_id
                        )
                        if device_token and has_client:
                            await _update_device_status(
                                device_token, DEVICE_STATUS_ACTIVE
                            )
                if message_type == "ice":
                    target_session_id = payload.get("session_id") or session_id
            await registry.touch(session_id)
            if target_session_id != session_id:
                await registry.touch(target_session_id)
            await registry.forward(target_session_id, role, message)
    except WebSocketDisconnect:
        logger.info("Disconnected %s for session %s from %s", role, session_id, _client_label(websocket))
    except Exception:
        logger.exception("WebSocket error for session %s (%s)", session_id, role)
    finally:
        if role == "client":
            _, _, device_token = await registry.get_session_state(session_id)
            if device_token:
                await _update_device_status(device_token, DEVICE_STATUS_DISCONNECTED)
        elif role == "browser":
            _, has_client, device_token = await registry.get_session_state(session_id)
            if device_token and has_client:
                await _update_device_status(device_token, DEVICE_STATUS_INACTIVE)
        await registry.unregister(session_id, role, websocket)


if __name__ == "__main__":
    uvicorn.run(app, host=SIGNALING_HOST, port=SIGNALING_PORT)
