import os
from typing import Any

import requests


DEFAULT_API_URL = os.getenv("RC_API_URL", "http://79.137.194.213").rstrip("/")
DEFAULT_API_TOKEN = os.getenv("RC_API_TOKEN", "Gar8tEadNew0l-DNgY36moO3o_3xRsmF7yhrgRSOMIA").strip()
DEFAULT_TIMEOUT = float(os.getenv("RC_API_TIMEOUT", "5"))


class RemoteControllerApi:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self._token = DEFAULT_API_TOKEN if token is None else token
        self._timeout = DEFAULT_TIMEOUT if timeout is None else timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._token:
            headers["x-rc-token"] = self._token
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    def fetch_clients(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/remote-clients") or {}
        return list(payload.get("clients", []))

    def ping(self) -> None:
        self._request("GET", "/api/health")

    def download_error_log(self) -> bytes:
        url = f"{self._base_url}/api/logs/error"
        params: dict[str, str] | None = None
        if self._token:
            params = {"token": self._token}
        response = requests.get(
            url,
            headers=self._headers(),
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.content

    def fetch_ice_servers(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/ice-config") or {}
        servers = payload.get("iceServers", [])
        if isinstance(servers, list):
            return servers
        return []

    def authenticate_operator(self, account_id: str, password: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/auth/login",
            {"account_id": account_id, "password": password},
        ) or {}
        return dict(payload.get("operator") or {})

    def update_client_name(self, client_id: str, name: str) -> None:
        self._request("PATCH", f"/api/remote-clients/{client_id}", {"name": name})

    def assign_client(self, client_id: str, operator_id: str, team_id: str) -> None:
        self._request(
            "PATCH",
            f"/api/remote-clients/{client_id}",
            {"assigned_operator_id": operator_id, "assigned_team_id": team_id},
        )

    def update_client_work_status(self, client_id: str, work_status: str) -> None:
        self._request(
            "PATCH",
            f"/api/remote-clients/{client_id}",
            {"work_status": work_status},
        )

    def update_client_tags(self, client_id: str, tag_ids: list[str]) -> None:
        self._request(
            "PATCH",
            f"/api/remote-clients/{client_id}",
            {"tag_ids": tag_ids},
        )

    def delete_client(self, client_id: str) -> None:
        self._request("DELETE", f"/api/remote-clients/{client_id}")

    def fetch_teams(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/teams") or {}
        return list(payload.get("teams", []))

    def fetch_operator(self, operator_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/operators/{operator_id}") or {}
        return dict(payload.get("operator") or {})

    def create_team(self, name: str, activity: bool | None = None) -> str:
        payload: dict[str, Any] = {"name": name}
        if activity is not None:
            payload["activity"] = activity
        response = self._request("POST", "/api/teams", payload) or {}
        team = response.get("team", {})
        return team.get("id", "")

    def update_team_name(self, team_id: str, name: str) -> None:
        self._request("PATCH", f"/api/teams/{team_id}", {"name": name})

    def update_team_activity(self, team_id: str, activity: bool) -> None:
        self._request("PATCH", f"/api/teams/{team_id}", {"activity": activity})

    def delete_team(self, team_id: str) -> None:
        self._request("DELETE", f"/api/teams/{team_id}")

    def create_team_tag(self, team_id: str, name: str, color: str) -> dict[str, Any]:
        payload = {"name": name, "color": color}
        response = self._request("POST", f"/api/teams/{team_id}/tags", payload) or {}
        return dict(response.get("tag") or {})

    def delete_team_tag(self, tag_id: str) -> None:
        self._request("DELETE", f"/api/team-tags/{tag_id}")

    def update_team_tag(
        self,
        tag_id: str,
        name: str | None = None,
        color: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if color is not None:
            payload["color"] = color
        self._request("PATCH", f"/api/team-tags/{tag_id}", payload)

    def upsert_operator(
        self,
        operator_id: str,
        name: str,
        password: str,
        role: str,
        team: str | None,
    ) -> None:
        self._request(
            "PUT",
            f"/api/operators/{operator_id}",
            {
                "name": name,
                "password": password,
                "role": role,
                "team": team,
            },
        )

    def update_operator_profile(
        self,
        operator_id: str,
        name: str | None = None,
        password: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if password is not None:
            payload["password"] = password
        self._request("PATCH", f"/api/operators/{operator_id}", payload)

    def update_operator_login(self, operator_id: str, new_login: str) -> None:
        self._request(
            "PATCH",
            f"/api/operators/{operator_id}/login",
            {"account_id": new_login},
        )

    def delete_operator(self, operator_id: str) -> None:
        self._request("DELETE", f"/api/operators/{operator_id}")

    # Activity Logs API

    def fetch_activity_logs(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
        entry_type: str | None = None,
        application: str | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch activity logs for a client session."""
        params: list[str] = []
        if limit:
            params.append(f"limit={limit}")
        if offset:
            params.append(f"offset={offset}")
        if entry_type:
            params.append(f"entry_type={entry_type}")
        if application:
            params.append(f"application={application}")
        if search:
            params.append(f"search={search}")
        if start_date:
            params.append(f"start_date={start_date}")
        if end_date:
            params.append(f"end_date={end_date}")
        
        query = "&".join(params)
        path = f"/api/activity-logs/{session_id}"
        if query:
            path += f"?{query}"
        
        return self._request("GET", path) or {"logs": [], "total": 0}

    def fetch_activity_applications(self, session_id: str) -> list[str]:
        """Fetch list of unique applications for a session."""
        payload = self._request("GET", f"/api/activity-logs/{session_id}/applications") or {}
        return list(payload.get("applications", []))

    def delete_activity_logs(
        self,
        session_id: str,
        log_ids: list[int] | None = None,
    ) -> int:
        """Delete activity logs for a session."""
        payload: dict[str, Any] | None = None
        if log_ids:
            payload = {"log_ids": log_ids}
        response = self._request("DELETE", f"/api/activity-logs/{session_id}", payload) or {}
        return response.get("deleted", 0)
