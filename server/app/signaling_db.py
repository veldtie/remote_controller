import asyncio
import json
import logging

import asyncpg

import signaling_config as config


logger = logging.getLogger("signaling_server")

db_pool: asyncpg.Pool | None = None

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
    CREATE TABLE IF NOT EXISTS team_tags (
        id TEXT PRIMARY KEY,
        team_id TEXT REFERENCES teams(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        color TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS team_tags_unique
    ON team_tags (team_id, lower(name));
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
        first_connected_at TIMESTAMPTZ,
        work_status TEXT NOT NULL DEFAULT 'planning',
        assigned_operator_id TEXT,
        assigned_team_id TEXT,
        ip TEXT,
        region TEXT,
        client_config JSONB
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS client_tags (
        client_id TEXT REFERENCES remote_clients(id) ON DELETE CASCADE,
        tag_id TEXT REFERENCES team_tags(id) ON DELETE CASCADE,
        PRIMARY KEY (client_id, tag_id)
    );
    """,
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW();",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS first_connected_at TIMESTAMPTZ;",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS work_status TEXT NOT NULL DEFAULT 'planning';",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS assigned_operator_id TEXT;",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS assigned_team_id TEXT;",
    "ALTER TABLE remote_clients ADD COLUMN IF NOT EXISTS client_config JSONB;",
]


async def init_db() -> None:
    """Initialize the asyncpg pool and schema when configured."""
    global db_pool
    if not config.DATABASE_URL:
        logger.info("Database disabled (RC_DATABASE_URL not set).")
        return
    for attempt in range(1, config.DB_CONNECT_RETRIES + 1):
        try:
            db_pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=config.DB_POOL_MIN,
                max_size=config.DB_POOL_MAX,
                statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,
            )
            async with db_pool.acquire() as conn:
                for statement in DEVICE_REGISTRY_SCHEMA + REMOTE_CONTROLLER_SCHEMA:
                    await conn.execute(statement)
                await conn.execute(
                    """
                    UPDATE remote_clients
                    SET first_connected_at = COALESCE(
                        first_connected_at,
                        (
                            SELECT MIN(created_at)
                            FROM device_registry
                            WHERE device_registry.session_id = remote_clients.id
                        )
                    )
                    WHERE first_connected_at IS NULL;
                    """
                )
            logger.info("Database connection established.")
            return
        except Exception:
            logger.exception("Database connection failed (attempt %s).", attempt)
            await asyncio.sleep(min(5, attempt))
    raise RuntimeError("Database connection failed after retries.")


async def close_db() -> None:
    """Close the database pool if initialized."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


async def upsert_device(
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


async def update_device_status(device_token: str, status: str) -> None:
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


async def touch_device_last_seen(device_token: str) -> None:
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


async def upsert_remote_client(
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
                    first_connected_at,
                    client_config
                )
                VALUES (
                    $1,
                    $1,
                    $2,
                    0,
                    $3,
                    $4,
                    $5,
                    NOW(),
                    CASE WHEN $2 = 'connected' THEN NOW() ELSE NULL END,
                    $6::jsonb
                )
                ON CONFLICT (id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    ip = COALESCE(EXCLUDED.ip, remote_clients.ip),
                    assigned_team_id = COALESCE(remote_clients.assigned_team_id, EXCLUDED.assigned_team_id),
                    assigned_operator_id = COALESCE(remote_clients.assigned_operator_id, EXCLUDED.assigned_operator_id),
                    client_config = CASE
                        WHEN EXCLUDED.client_config IS NULL THEN remote_clients.client_config
                        WHEN remote_clients.client_config IS NULL THEN EXCLUDED.client_config
                        ELSE remote_clients.client_config || EXCLUDED.client_config
                    END,
                    first_connected_at = CASE
                        WHEN remote_clients.first_connected_at IS NULL
                             AND EXCLUDED.status = 'connected' THEN NOW()
                        ELSE remote_clients.first_connected_at
                    END,
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


async def update_connected_time() -> None:
    """Persist connected time for remote clients every tick."""
    if config.CONNECTED_TIME_INTERVAL <= 0:
        return
    interval = max(1.0, config.CONNECTED_TIME_INTERVAL)
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
