import json
import logging
import os
import secrets
from typing import Any


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

DEVICE_STATUS_ACTIVE = "active"
DEVICE_STATUS_INACTIVE = "inactive"
DEVICE_STATUS_DISCONNECTED = "disconnected"
KEEPALIVE_MESSAGE_TYPES = {"ping", "pong", "keepalive"}

logger = logging.getLogger("signaling_server")


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


def _normalize_ice_servers(value: Any) -> list[dict[str, object]]:
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


def is_valid_signaling_token(provided_token: str | None) -> bool:
    """Accept the signaling token or the API token when signaling auth is enabled."""
    if not SIGNALING_TOKEN:
        return True
    if provided_token == SIGNALING_TOKEN:
        return True
    if API_TOKEN and provided_token == API_TOKEN:
        return True
    return False


def extract_forwarded_ip(headers) -> str | None:
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return None


def resolve_client_ip(headers, client) -> str | None:
    if TRUST_PROXY:
        forwarded = extract_forwarded_ip(headers)
        if forwarded:
            return forwarded
    if client:
        return client.host
    return None
