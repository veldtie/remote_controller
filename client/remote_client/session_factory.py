"""Session resource factory for remote connections."""
from __future__ import annotations

from typing import Any

from remote_client.control.handlers import ControlHandler
from remote_client.control.input_controller import InputController, NullInputController
from remote_client.media.audio import AudioTrack
from remote_client.media.screen import ScreenTrack


def _normalize_mode(mode: str | None) -> str:
    if not mode:
        return "manage"
    value = str(mode).strip().lower()
    if value in {"view", "viewer", "readonly"}:
        return "view"
    return "manage"


def build_session_resources(mode: str | None) -> tuple[ControlHandler, list[Any]]:
    normalized = _normalize_mode(mode)
    if normalized == "view":
        controller = NullInputController()
        screen_track = ScreenTrack()
    else:
        controller = InputController()
        screen_track = ScreenTrack(draw_cursor=False)

    control_handler = ControlHandler(controller)
    media_tracks: list[Any] = [screen_track, AudioTrack()]
    return control_handler, media_tracks
