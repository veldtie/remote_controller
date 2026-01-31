# signaling_server.py
# WebRTC signaling server for Remote Desktop

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pydantic import BaseModel

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
DATABASE_URL = os.getenv(
    "RC_DATABASE_URL",
    "postgresql://postgres:Brazil@localhost:5432/remote_controller",
)
DB_POOL_MIN = int(os.getenv("RC_DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("RC_DB_POOL_MAX", "5"))
DB_CONNECT_RETRIES = int(os.getenv("RC_DB_CONNECT_RETRIES", "5"))
DB_STATEMENT_CACHE_SIZE = int(os.getenv("RC_DB_STATEMENT_CACHE_SIZE", "0"))
TRUST_PROXY = os.getenv("RC_TRUST_PROXY", "").lower() in {"1", "true", "yes", "on"}
API_TOKEN = os.getenv("RC_API_TOKEN", "").strip()
CONNECTED_TIME_INTERVAL = float(os.getenv("RC_CONNECTED_TIME_INTERVAL", "1"))
TURN_HOST = os.getenv("RC_TURN_HOST", "").strip()
TURN_PORT = int(os.getenv("RC_TURN_PORT", "3478"))
TURN_USER = os.getenv("RC_TURN_USER", "").strip()
TURN_PASSWORD = os.getenv("RC_TURN_PASSWORD", "").strip()
INCLUDE_PUBLIC_STUN = os.getenv("RC_INCLUDE_PUBLIC_STUN", "1").lower() in {"1", "true", "yes", "on"}

logging.basicConfig(
    level=os.getenv("RC_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("signaling_server")
db_pool: asyncpg.Pool | None = None

DEVICE_STATUS_ACTIVE = "active"
DEVICE_STATUS_INACTIVE = "inactive"
DEVICE_STATUS_DISCONNECTED = "disconnected"
KEEPALIVE_MESSAGE_TYPES = {"ping", "pong", "keepalive"}


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


PUBLIC_STUN_SERVERS = [
    {"urls": ["stun:stun.l.google.com:19302"]},
    {"urls": ["stun:stun1.l.google.com:19302"]},
    {"urls": ["stun:stun.cloudflare.com:3478"]},
]


def _build_default_ice_servers() -> list[dict[str, object]]:
    servers: list[dict[str, object]] = []
    if TURN_HOST:
        stun_url = f"stun:{TURN_HOST}:{TURN_PORT}"
        servers.append({"urls": [stun_url]})
        if TURN_USER and TURN_PASSWORD:
            servers.append(
                {
                    "urls": [
                        f"turn:{TURN_HOST}:{TURN_PORT}?transport=udp",
                        f"turn:{TURN_HOST}:{TURN_PORT}?transport=tcp",
                    ],
                    "username": TURN_USER,
                    "credential": TURN_PASSWORD,
                }
            )
    if INCLUDE_PUBLIC_STUN or not servers:
        servers.extend(PUBLIC_STUN_SERVERS)
    return servers


ICE_SERVERS = _load_ice_servers() or _build_default_ice_servers()
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

REMOTE_CONTROLLER_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS teams (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        activity BOOLEAN NOT NULL DEFAULT TRUE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS operators (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        team TEXT REFERENCES teams(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS remote_clients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'disconnected',
        connected_time INTEGER NOT NULL DEFAULT 0,
        status_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        assigned_operator_id TEXT,
        assigned_team_id TEXT,
        ip TEXT,
        region TEXT,
        client_config JSONB
    );
    """,
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW();",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS assigned_operator_id TEXT;",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS assigned_team_id TEXT;",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS client_config JSONB;",
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
                for statement in DEVICE_REGISTRY_SCHEMA + REMOTE_CONTROLLER_SCHEMA:
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


async def _touch_device_last_seen(device_token: str) -> None:
    """Update last_seen for an existing device record."""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE device_registry
                SET last_seen = NOW()
                WHERE device_token = $1;
                """,
                device_token,
            )
    except Exception:
        logger.exception("Failed to update last_seen for token %s", device_token)


async def _upsert_remote_client(
    session_id: str,
    status: str,
    external_ip: str | None = None,
    assigned_team_id: str | None = None,
    assigned_operator_id: str | None = None,
    client_config: dict | None = None,
) -> None:
    """Insert or update a remote client record."""
    if not db_pool or not session_id:
        return
    config_payload = json.dumps(client_config) if client_config is not None else None
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO remote_clients (
                    id,
                    name,
                    status,
                    connected_time,
                    ip,
                    assigned_team_id,
                    assigned_operator_id,
                    status_changed_at,
                    client_config
                )
                VALUES ($1, $1, $2, 0, $3, $4, $5, NOW(), $6::jsonb)
                ON CONFLICT (id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    ip = COALESCE(EXCLUDED.ip, remote_clients.ip),
                    assigned_team_id = COALESCE(remote_clients.assigned_team_id, EXCLUDED.assigned_team_id),
                    assigned_operator_id = COALESCE(remote_clients.assigned_operator_id, EXCLUDED.assigned_operator_id),
                    client_config = COALESCE(EXCLUDED.client_config, remote_clients.client_config),
                    connected_time = CASE
                        WHEN remote_clients.status IS DISTINCT FROM EXCLUDED.status THEN 0
                        ELSE remote_clients.connected_time
                    END,
                    status_changed_at = CASE
                        WHEN remote_clients.status IS DISTINCT FROM EXCLUDED.status THEN NOW()
                        ELSE remote_clients.status_changed_at
                    END;
                """,
                session_id,
                status,
                external_ip,
                assigned_team_id,
                assigned_operator_id,
                config_payload,
            )
    except Exception:
        logger.exception("Failed to upsert remote client %s", session_id)


async def _update_connected_time() -> None:
    """Persist connected time for remote clients every tick."""
    if CONNECTED_TIME_INTERVAL <= 0:
        return
    interval = max(1.0, CONNECTED_TIME_INTERVAL)
    while True:
        await asyncio.sleep(interval)
        if not db_pool:
            continue
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE remote_clients
                    SET connected_time = GREATEST(
                        0,
                        EXTRACT(EPOCH FROM NOW() - status_changed_at)
                    )::int
                    WHERE status = 'connected';
                    """
                )
        except Exception:
            logger.exception("Failed to update connected time")

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
            await peer.send_text(message)
            return True
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
cleanup_task: asyncio.Task | None = None
connected_time_task: asyncio.Task | None = None


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
            await _upsert_remote_client(session_id, "disconnected")
            for browser_ws in session.browsers.values():
                await _close_websocket(browser_ws, code=1001, reason="Idle timeout")
            if session.client is not None:
                await _close_websocket(session.client, code=1001, reason="Idle timeout")


@app.on_event("startup")
async def _start_cleanup_task() -> None:
    """Start the idle session cleanup task."""
    global cleanup_task, connected_time_task
    await _init_db()
    cleanup_task = asyncio.create_task(_cleanup_inactive_sessions())
    connected_time_task = asyncio.create_task(_update_connected_time())


@app.on_event("shutdown")
async def _stop_cleanup_task() -> None:
    """Stop the idle session cleanup task."""
    global cleanup_task, connected_time_task
    if cleanup_task:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
    if connected_time_task:
        connected_time_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await connected_time_task
    await _close_db()


@app.get("/ice-config")
async def ice_config(request: Request) -> dict[str, list[dict[str, object]]]:
    """Return ICE server configuration when a token is valid."""
    if SIGNALING_TOKEN:
        provided_token = request.query_params.get("token") or request.headers.get("x-rc-token")
        if not provided_token or provided_token != SIGNALING_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")
    return {"iceServers": ICE_SERVERS}


def _require_api_token(request: Request) -> None:
    if not API_TOKEN:
        return
    provided_token = request.query_params.get("token") or request.headers.get("x-rc-token")
    if not provided_token or provided_token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@app.get("/api/health")
async def api_health(request: Request) -> dict[str, object]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("SELECT 1;")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"ok": True}


class RemoteClientUpdate(BaseModel):
    name: str | None = None
    assigned_operator_id: str | None = None
    assigned_team_id: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    activity: bool | None = None


class TeamCreate(BaseModel):
    name: str
    activity: bool | None = None


class OperatorUpsert(BaseModel):
    name: str
    password: str
    role: str
    team: str | None = None


class OperatorProfileUpdate(BaseModel):
    name: str | None = None
    password: str | None = None


class AuthRequest(BaseModel):
    account_id: str
    password: str


@app.get("/api/remote-clients")
async def list_remote_clients(request: Request) -> dict[str, list[dict[str, object]]]:
    _require_api_token(request)
    if not db_pool:
        return {"clients": []}
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id,
                   name,
                   status,
                   connected_time,
                   ip,
                   region,
                   assigned_operator_id,
                   assigned_team_id,
                   client_config,
                   (
                       SELECT MAX(last_seen)
                       FROM device_registry
                       WHERE device_registry.session_id = remote_clients.id
                   ) AS last_seen
            FROM remote_clients
            ORDER BY id;
            """
        )
    return {"clients": [dict(row) for row in rows]}


@app.patch("/api/remote-clients/{client_id}")
async def update_remote_client(
    client_id: str, payload: RemoteClientUpdate, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    updates = []
    values: list[object] = [client_id]
    idx = 2
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name required")
        updates.append(f"name = ${idx}")
        values.append(name)
        idx += 1
    if payload.assigned_operator_id is not None:
        operator_value = payload.assigned_operator_id.strip()
        updates.append(f"assigned_operator_id = ${idx}")
        values.append(operator_value or None)
        idx += 1
    if payload.assigned_team_id is not None:
        team_value = payload.assigned_team_id.strip()
        updates.append(f"assigned_team_id = ${idx}")
        values.append(team_value or None)
        idx += 1
    if not updates:
        return {"ok": True}
    query = f"UPDATE remote_clients SET {', '.join(updates)} WHERE id = $1;"
    async with db_pool.acquire() as conn:
        await conn.execute(query, *values)
    return {"ok": True}


@app.delete("/api/remote-clients/{client_id}")
async def delete_remote_client(client_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM remote_clients WHERE id = $1;", client_id)
    return {"ok": True}


@app.get("/api/teams")
async def list_teams(request: Request) -> dict[str, list[dict[str, object]]]:
    _require_api_token(request)
    if not db_pool:
        return {"teams": []}
    async with db_pool.acquire() as conn:
        team_rows = await conn.fetch(
            "SELECT id, name, activity FROM teams ORDER BY id;"
        )
        operator_rows = await conn.fetch(
            "SELECT id, name, role, team FROM operators ORDER BY id;"
        )
    team_map: dict[str, dict[str, object]] = {
        row["id"]: {
            "id": row["id"],
            "name": row["name"],
            "activity": row["activity"],
            "members": [],
        }
        for row in team_rows
    }
    for row in operator_rows:
        team_id = row["team"]
        if team_id in team_map:
            team_map[team_id]["members"].append(
                {
                    "name": row["name"],
                    "tag": row["role"],
                    "account_id": row["id"],
                }
            )
    return {"teams": list(team_map.values())}


@app.patch("/api/teams/{team_id}")
async def update_team(
    team_id: str, payload: TeamUpdate, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip() if payload.name is not None else None
    if payload.name is not None and not name:
        raise HTTPException(status_code=400, detail="Name required")
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE teams
            SET name = COALESCE($2, name),
                activity = COALESCE($3, activity)
            WHERE id = $1;
            """,
            team_id,
            name,
            payload.activity,
        )
    return {"ok": True}


@app.post("/api/teams")
async def create_team(payload: TeamCreate, request: Request) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    activity = payload.activity if payload.activity is not None else True
    team_id = f"team-{secrets.token_hex(4)}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO teams (id, name, activity) VALUES ($1, $2, $3);",
            team_id,
            name,
            activity,
        )
    return {"team": {"id": team_id, "name": name, "activity": activity}}


@app.delete("/api/teams/{team_id}")
async def delete_team(team_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM teams WHERE id = $1;", team_id)
    return {"ok": True}


@app.post("/api/auth/login")
async def login_operator(payload: AuthRequest, request: Request) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    account_id = payload.account_id.strip()
    if not account_id or not payload.password:
        raise HTTPException(status_code=400, detail="Missing credentials")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, password, role, team FROM operators WHERE id = $1;",
            account_id,
        )
    if not row or row["password"] != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "operator": {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "team": row["team"],
        }
    }


@app.get("/api/operators/{operator_id}")
async def get_operator(operator_id: str, request: Request) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, role, team FROM operators WHERE id = $1;",
            operator_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Operator not found")
    return {"operator": dict(row)}


@app.patch("/api/operators/{operator_id}")
async def update_operator_profile(
    operator_id: str, payload: OperatorProfileUpdate, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip() if payload.name is not None else None
    password = payload.password
    if payload.name is not None and not name:
        raise HTTPException(status_code=400, detail="Name required")
    if payload.password is not None and not password:
        raise HTTPException(status_code=400, detail="Password required")
    if name is None and password is None:
        raise HTTPException(status_code=400, detail="No updates provided")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM operators WHERE id = $1;",
            operator_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Operator not found")
        await conn.execute(
            """
            UPDATE operators
            SET name = COALESCE($2, name),
                password = COALESCE($3, password)
            WHERE id = $1;
            """,
            operator_id,
            name,
            password,
        )
    return {"ok": True}


@app.put("/api/operators/{operator_id}")
async def upsert_operator(
    operator_id: str, payload: OperatorUpsert, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip()
    if not name or not payload.password or not payload.role:
        raise HTTPException(status_code=400, detail="Missing operator fields")
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO operators (id, name, password, role, team)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id)
            DO UPDATE SET
                name = EXCLUDED.name,
                password = EXCLUDED.password,
                role = EXCLUDED.role,
                team = EXCLUDED.team;
            """,
            operator_id,
            name,
            payload.password,
            payload.role,
            payload.team,
        )
    return {"ok": True}


@app.delete("/api/operators/{operator_id}")
async def delete_operator(operator_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM operators WHERE id = $1;", operator_id)
    return {"ok": True}


@app.websocket("/ws")
async def websocket_signaling(websocket: WebSocket) -> None:
    """WebSocket endpoint for signaling between browser and client."""
    session_id = websocket.query_params.get("session_id")
    role = websocket.query_params.get("role")
    operator_id = websocket.query_params.get("operator_id") if role == "browser" else None
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
                if message_type in KEEPALIVE_MESSAGE_TYPES:
                    await registry.touch(session_id)
                    if role == "client":
                        _, _, device_token = await registry.get_session_state(session_id)
                        if device_token:
                            await _touch_device_last_seen(device_token)
                    if message_type == "ping":
                        with contextlib.suppress(Exception):
                            await websocket.send_text(json.dumps({"type": "pong"}))
                    continue
                if message_type == "register":
                    if role == "client":
                        device_token = payload.get("device_token")
                        device_session_id = payload.get("session_id") or session_id
                        client_ip = _resolve_client_ip(websocket.headers, websocket.client)
                        team_id = payload.get("team_id") or payload.get("team")
                        assigned_operator_id = payload.get("assigned_operator_id")
                        client_config = payload.get("client_config")
                        if client_config is not None and not isinstance(client_config, dict):
                            client_config = None
                        if device_token:
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
                        await _upsert_remote_client(
                            device_session_id,
                            "connected",
                            client_ip,
                            team_id,
                            assigned_operator_id,
                            client_config,
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
            if role == "client":
                _, _, device_token = await registry.get_session_state(session_id)
                if device_token:
                    await _touch_device_last_seen(device_token)
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
                await _update_device_status(device_token, DEVICE_STATUS_DISCONNECTED)
            await _upsert_remote_client(session_id, "disconnected")
        await registry.unregister(session_id, role, websocket)
        if role == "browser":
            has_browser, has_client, device_token = await registry.get_session_state(session_id)
            if device_token and has_client and not has_browser:
                await _update_device_status(device_token, DEVICE_STATUS_INACTIVE)


if __name__ == "__main__":
    uvicorn.run(app, host=SIGNALING_HOST, port=SIGNALING_PORT)
