import os
from typing import Any

import requests


DEFAULT_API_URL = os.getenv("RC_API_URL", "http://79.137.194.213").rstrip("/")
DEFAULT_API_TOKEN = os.getenv("RC_API_TOKEN", "Gar8tEadNew0l-DNgY36moO3o_3xRsmF7yhrgRSOMIA").strip()
DEFAULT_TIMEOUT = float(os.getenv("RC_API_TIMEOUT", "3"))


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

    def update_client_name(self, client_id: str, name: str) -> None:
        self._request("PATCH", f"/api/remote-clients/{client_id}", {"name": name})

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

    def delete_operator(self, operator_id: str) -> None:
        self._request("DELETE", f"/api/operators/{operator_id}")
