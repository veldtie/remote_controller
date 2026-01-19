"""Runtime helpers for building the remote client."""
from __future__ import annotations

import os
import uuid

from remote_client.files.file_service import FileService
from remote_client.security.e2ee import load_e2ee_context
from remote_client.session_factory import build_session_resources
from remote_client.webrtc.client import WebRTCClient
from remote_client.webrtc.signaling import create_signaling, create_signaling_from_url


def load_or_create_device_token() -> str | None:
    env_token = os.getenv("RC_DEVICE_TOKEN")
    if env_token:
        return env_token.strip()

    token_path = os.getenv("RC_DEVICE_TOKEN_PATH")
    if token_path:
        token_path = os.path.expanduser(token_path)
    else:
        token_path = os.path.join(os.path.expanduser("~"), ".remote_controller", "device_token")

    try:
        with open(token_path, "r", encoding="utf-8") as handle:
            stored = handle.read().strip()
            if stored:
                return stored
    except FileNotFoundError:
        pass
    except OSError:
        return None

    device_token = uuid.uuid4().hex
    try:
        token_dir = os.path.dirname(token_path)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as handle:
            handle.write(device_token)
    except OSError:
        return device_token
    return device_token


def build_client(session_id: str, token: str | None, device_token: str | None) -> WebRTCClient:
    signaling_url = os.getenv("RC_SIGNALING_URL")
    if signaling_url:
        if "://" in signaling_url:
            signaling = create_signaling_from_url(signaling_url, session_id, token)
        else:
            host, _, port = signaling_url.partition(":")
            signaling = create_signaling(
                host,
                int(port) if port else int(os.getenv("RC_SIGNALING_PORT", "8000")),
                session_id,
                token,
            )
    else:
        signaling_host = os.getenv("RC_SIGNALING_HOST", "localhost")
        signaling_port = int(os.getenv("RC_SIGNALING_PORT", "8000"))
        signaling = create_signaling(signaling_host, signaling_port, session_id, token)

    file_service = FileService()
    e2ee_context = load_e2ee_context(session_id)
    return WebRTCClient(
        session_id=session_id,
        signaling=signaling,
        session_factory=build_session_resources,
        file_service=file_service,
        device_token=device_token,
        e2ee=e2ee_context,
    )
