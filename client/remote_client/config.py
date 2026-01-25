"""Configuration helpers for the remote client."""
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass

TEAM_ID_FILENAME = "rc_team_id.txt"
ANTIFRAUD_CONFIG_FILENAME = "rc_antifraud.json"

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
    candidate_dirs = []
    if getattr(sys, "frozen", False):
        candidate_dirs.append(os.path.dirname(sys.executable))
    candidate_dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for base_dir in candidate_dirs:
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
    candidate_dirs = []
    if getattr(sys, "frozen", False):
        candidate_dirs.append(os.path.dirname(sys.executable))
    candidate_dirs.append(os.path.dirname(os.path.abspath(__file__)))
    for base_dir in candidate_dirs:
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
