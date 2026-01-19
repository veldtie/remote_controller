"""Configuration helpers for the remote client."""
from __future__ import annotations

import os
import uuid


def resolve_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    env_session = os.getenv("RC_SIGNALING_SESSION")
    if env_session:
        return env_session
    return uuid.uuid4().hex
