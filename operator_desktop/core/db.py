from __future__ import annotations

import logging
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


logger = logging.getLogger(__name__)


DEFAULT_DB_URL = os.getenv(
    "RC_DATABASE_URL",
    "postgresql://postgres:Brazil@localhost:5432/remote_controller",
)


class RemoteControllerRepository:
    def __init__(self, db_url: str | None = None) -> None:
        self._db_url = db_url or DEFAULT_DB_URL

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._db_url, autocommit=True, row_factory=dict_row)

    def load_clients(self) -> list[dict[str, Any]]:
        query = """
            SELECT id, name, status, connected_time, ip, region
            FROM remote_clients
            ORDER BY id;
        """
        try:
            with self._connect() as conn:
                return conn.execute(query).fetchall()
        except Exception as exc:
            logger.warning("Failed to load remote clients: %s", exc)
            return []

    def load_teams(self) -> list[dict[str, Any]]:
        try:
            with self._connect() as conn:
                teams = conn.execute(
                    "SELECT id, name, activity FROM teams ORDER BY id;"
                ).fetchall()
                operators = conn.execute(
                    "SELECT id, name, password, role, team FROM operators ORDER BY id;"
                ).fetchall()
        except Exception as exc:
            logger.warning("Failed to load teams: %s", exc)
            return []

        members_by_team: dict[str, list[dict[str, Any]]] = {}
        for operator in operators:
            team_id = operator.get("team")
            if not team_id:
                continue
            members_by_team.setdefault(team_id, []).append(
                {
                    "name": operator.get("name", ""),
                    "tag": operator.get("role", "operator"),
                    "account_id": operator.get("id", ""),
                    "password": operator.get("password", ""),
                }
            )

        result = []
        for team in teams:
            team_id = team.get("id")
            result.append(
                {
                    "id": team_id,
                    "name": team.get("name", ""),
                    "activity": bool(team.get("activity", True)),
                    "members": members_by_team.get(team_id, []),
                }
            )
        return result

    def update_client_name(self, client_id: str, name: str) -> None:
        query = "UPDATE remote_clients SET name = %s WHERE id = %s;"
        self._execute(query, (name, client_id))

    def update_client_status(self, client_id: str, status: str, connected_time: int) -> None:
        query = """
            UPDATE remote_clients
            SET status = %s, connected_time = %s
            WHERE id = %s;
        """
        self._execute(query, (status, connected_time, client_id))

    def delete_client(self, client_id: str) -> None:
        query = "DELETE FROM remote_clients WHERE id = %s;"
        self._execute(query, (client_id,))

    def update_team_name(self, team_id: str, name: str) -> None:
        query = "UPDATE teams SET name = %s WHERE id = %s;"
        self._execute(query, (name, team_id))

    def update_team_activity(self, team_id: str, activity: bool) -> None:
        query = "UPDATE teams SET activity = %s WHERE id = %s;"
        self._execute(query, (activity, team_id))

    def upsert_operator(
        self, operator_id: str, name: str, password: str, role: str, team: str
    ) -> None:
        query = """
            INSERT INTO operators (id, name, password, role, team)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                password = EXCLUDED.password,
                role = EXCLUDED.role,
                team = EXCLUDED.team;
        """
        self._execute(query, (operator_id, name, password, role, team))

    def delete_operator(self, operator_id: str) -> None:
        query = "DELETE FROM operators WHERE id = %s;"
        self._execute(query, (operator_id,))

    def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        try:
            with self._connect() as conn:
                conn.execute(query, params)
        except Exception as exc:
            logger.warning("Database write failed: %s", exc)
