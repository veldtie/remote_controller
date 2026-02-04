import secrets
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

import signaling_config as config
import signaling_db


router = APIRouter()
WORK_STATUSES = {"planning", "in_work", "worked_out"}


@router.get("/ice-config")
async def ice_config(request: Request) -> dict[str, list[dict[str, object]]]:
    """Return ICE server configuration when a token is valid."""
    if config.SIGNALING_TOKEN:
        provided_token = request.query_params.get("token") or request.headers.get("x-rc-token")
        if not config.is_valid_signaling_token(provided_token):
            raise HTTPException(status_code=403, detail="Invalid token")
    return {"iceServers": config.ICE_SERVERS}


def _require_api_token(request: Request) -> None:
    if not config.API_TOKEN:
        return
    provided_token = request.query_params.get("token") or request.headers.get("x-rc-token")
    if not provided_token or provided_token != config.API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@router.get("/api/health")
async def api_health(request: Request) -> dict[str, object]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        async with signaling_db.db_pool.acquire() as conn:
            await conn.execute("SELECT 1;")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"ok": True}


@router.get("/api/logs/error")
async def download_error_log(request: Request) -> FileResponse:
    _require_api_token(request)
    log_path = Path(config.ERROR_LOG_FILE)
    if not log_path.is_absolute():
        log_path = (Path.cwd() / log_path).resolve()
    if not log_path.exists():
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.touch(exist_ok=True)
        except Exception:
            log_path = None
    if not log_path or not log_path.is_file():
        with NamedTemporaryFile(delete=False, suffix=".log") as temp:
            temp.write(b"No error log available.\n")
            temp_path = Path(temp.name)
        return FileResponse(
            temp_path,
            media_type="text/plain",
            filename=temp_path.name,
        )
    return FileResponse(log_path, media_type="text/plain", filename=log_path.name)


class RemoteClientUpdate(BaseModel):
    name: str | None = None
    assigned_operator_id: str | None = None
    assigned_team_id: str | None = None
    work_status: str | None = None
    tag_ids: list[str] | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    activity: bool | None = None


class TeamCreate(BaseModel):
    name: str
    activity: bool | None = None


class TeamTagCreate(BaseModel):
    name: str
    color: str


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


@router.get("/api/remote-clients")
async def list_remote_clients(request: Request) -> dict[str, list[dict[str, object]]]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        return {"clients": []}
    async with signaling_db.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT remote_clients.id,
                   remote_clients.name,
                   remote_clients.status,
                   remote_clients.connected_time,
                   remote_clients.ip,
                   remote_clients.region,
                   remote_clients.assigned_operator_id,
                   remote_clients.assigned_team_id,
                   remote_clients.client_config,
                   remote_clients.work_status,
                   (
                       SELECT MAX(last_seen)
                       FROM device_registry
                       WHERE device_registry.session_id = remote_clients.id
                   ) AS last_seen,
                   COALESCE(
                       remote_clients.first_connected_at,
                       (
                           SELECT MIN(created_at)
                           FROM device_registry
                           WHERE device_registry.session_id = remote_clients.id
                       )
                   ) AS created_at,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'id', team_tags.id,
                               'name', team_tags.name,
                               'color', team_tags.color
                           )
                       ) FILTER (WHERE team_tags.id IS NOT NULL),
                       '[]'
                   ) AS tags
            FROM remote_clients
            LEFT JOIN client_tags
              ON client_tags.client_id = remote_clients.id
            LEFT JOIN team_tags
              ON team_tags.id = client_tags.tag_id
            GROUP BY remote_clients.id
            ORDER BY remote_clients.id;
            """
        )
    return {"clients": [dict(row) for row in rows]}


@router.patch("/api/remote-clients/{client_id}")
async def update_remote_client(
    client_id: str, payload: RemoteClientUpdate, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
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
    if payload.work_status is not None:
        status_value = payload.work_status.strip().lower()
        if status_value not in WORK_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid work status")
        updates.append(f"work_status = ${idx}")
        values.append(status_value)
        idx += 1
    if not updates and payload.tag_ids is None:
        return {"ok": True}
    query = f"UPDATE remote_clients SET {', '.join(updates)} WHERE id = $1;"
    async with signaling_db.db_pool.acquire() as conn:
        async with conn.transaction():
            if updates:
                await conn.execute(query, *values)
            if payload.tag_ids is not None:
                tag_ids = [str(tag).strip() for tag in payload.tag_ids if str(tag).strip()]
                tag_ids = list(dict.fromkeys(tag_ids))
                team_row = await conn.fetchrow(
                    "SELECT assigned_team_id FROM remote_clients WHERE id = $1;",
                    client_id,
                )
                team_id = team_row["assigned_team_id"] if team_row else None
                valid_tag_ids: list[str] = []
                if team_id and tag_ids:
                    rows = await conn.fetch(
                        """
                        SELECT id
                        FROM team_tags
                        WHERE team_id = $1 AND id = ANY($2::text[]);
                        """,
                        team_id,
                        tag_ids,
                    )
                    valid_tag_ids = [row["id"] for row in rows]
                await conn.execute(
                    "DELETE FROM client_tags WHERE client_id = $1;",
                    client_id,
                )
                if valid_tag_ids:
                    await conn.executemany(
                        """
                        INSERT INTO client_tags (client_id, tag_id)
                        VALUES ($1, $2)
                        ON CONFLICT DO NOTHING;
                        """,
                        [(client_id, tag_id) for tag_id in valid_tag_ids],
                    )
    return {"ok": True}


@router.delete("/api/remote-clients/{client_id}")
async def delete_remote_client(client_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with signaling_db.db_pool.acquire() as conn:
        await conn.execute("DELETE FROM remote_clients WHERE id = $1;", client_id)
    return {"ok": True}


@router.get("/api/teams")
async def list_teams(request: Request) -> dict[str, list[dict[str, object]]]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        return {"teams": []}
    async with signaling_db.db_pool.acquire() as conn:
        team_rows = await conn.fetch(
            "SELECT id, name, activity FROM teams ORDER BY id;"
        )
        operator_rows = await conn.fetch(
            "SELECT id, name, role, team FROM operators ORDER BY id;"
        )
        tag_rows = await conn.fetch(
            "SELECT id, name, color, team_id FROM team_tags ORDER BY name;"
        )
    team_map: dict[str, dict[str, object]] = {
        row["id"]: {
            "id": row["id"],
            "name": row["name"],
            "activity": row["activity"],
            "members": [],
            "tags": [],
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
    for row in tag_rows:
        team_id = row["team_id"]
        if team_id in team_map:
            team_map[team_id].setdefault("tags", []).append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "color": row["color"],
                }
            )
    return {"teams": list(team_map.values())}


@router.patch("/api/teams/{team_id}")
async def update_team(
    team_id: str, payload: TeamUpdate, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip() if payload.name is not None else None
    if payload.name is not None and not name:
        raise HTTPException(status_code=400, detail="Name required")
    async with signaling_db.db_pool.acquire() as conn:
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


@router.post("/api/teams")
async def create_team(payload: TeamCreate, request: Request) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    activity = payload.activity if payload.activity is not None else True
    team_id = f"team-{secrets.token_hex(4)}"
    async with signaling_db.db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO teams (id, name, activity) VALUES ($1, $2, $3);",
            team_id,
            name,
            activity,
        )
    return {"team": {"id": team_id, "name": name, "activity": activity}}


@router.post("/api/teams/{team_id}/tags")
async def create_team_tag(
    team_id: str, payload: TeamTagCreate, request: Request
) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip()
    color = payload.color.strip()
    if not name or not color:
        raise HTTPException(status_code=400, detail="Name and color required")
    tag_id = f"tag-{secrets.token_hex(4)}"
    async with signaling_db.db_pool.acquire() as conn:
        team_row = await conn.fetchrow("SELECT id FROM teams WHERE id = $1;", team_id)
        if not team_row:
            raise HTTPException(status_code=404, detail="Team not found")
        exists = await conn.fetchrow(
            "SELECT 1 FROM team_tags WHERE team_id = $1 AND lower(name) = lower($2);",
            team_id,
            name,
        )
        if exists:
            raise HTTPException(status_code=409, detail="Tag already exists")
        await conn.execute(
            """
            INSERT INTO team_tags (id, team_id, name, color)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id)
            DO NOTHING;
            """,
            tag_id,
            team_id,
            name,
            color,
        )
    return {"tag": {"id": tag_id, "team_id": team_id, "name": name, "color": color}}


@router.delete("/api/teams/{team_id}")
async def delete_team(team_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with signaling_db.db_pool.acquire() as conn:
        await conn.execute("DELETE FROM teams WHERE id = $1;", team_id)
    return {"ok": True}


@router.delete("/api/team-tags/{tag_id}")
async def delete_team_tag(tag_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with signaling_db.db_pool.acquire() as conn:
        await conn.execute("DELETE FROM team_tags WHERE id = $1;", tag_id)
    return {"ok": True}


@router.post("/api/auth/login")
async def login_operator(payload: AuthRequest, request: Request) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    account_id = payload.account_id.strip()
    if not account_id or not payload.password:
        raise HTTPException(status_code=400, detail="Missing credentials")
    async with signaling_db.db_pool.acquire() as conn:
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


@router.get("/api/operators/{operator_id}")
async def get_operator(operator_id: str, request: Request) -> dict[str, dict[str, object]]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with signaling_db.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, role, team FROM operators WHERE id = $1;",
            operator_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Operator not found")
    return {"operator": dict(row)}


@router.patch("/api/operators/{operator_id}")
async def update_operator_profile(
    operator_id: str, payload: OperatorProfileUpdate, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip() if payload.name is not None else None
    password = payload.password
    if payload.name is not None and not name:
        raise HTTPException(status_code=400, detail="Name required")
    if payload.password is not None and not password:
        raise HTTPException(status_code=400, detail="Password required")
    if name is None and password is None:
        raise HTTPException(status_code=400, detail="No updates provided")
    async with signaling_db.db_pool.acquire() as conn:
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


@router.put("/api/operators/{operator_id}")
async def upsert_operator(
    operator_id: str, payload: OperatorUpsert, request: Request
) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    name = payload.name.strip()
    if not name or not payload.password or not payload.role:
        raise HTTPException(status_code=400, detail="Missing operator fields")
    async with signaling_db.db_pool.acquire() as conn:
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


@router.delete("/api/operators/{operator_id}")
async def delete_operator(operator_id: str, request: Request) -> dict[str, bool]:
    _require_api_token(request)
    if not signaling_db.db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with signaling_db.db_pool.acquire() as conn:
        await conn.execute("DELETE FROM operators WHERE id = $1;", operator_id)
    return {"ok": True}
