"""Configuration helpers for the remote client."""
from __future__ import annotations

import os
import sys
import uuid

TEAM_ID_FILENAME = "rc_team_id.txt"


def resolve_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    env_session = os.getenv("RC_SIGNALING_SESSION")
    if env_session:
        return env_session
    return uuid.uuid4().hex


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
