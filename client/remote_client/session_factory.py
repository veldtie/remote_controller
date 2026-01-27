"""Session resource factory for remote connections."""
from __future__ import annotations

from typing import Any

import logging
import os
import platform

from remote_client.control.handlers import ControlHandler
from remote_client.control.input_controller import InputController, NullInputController
from remote_client.media.audio import AudioTrack
from remote_client.media.screen import ScreenTrack
from remote_client.webrtc.client import SessionResources

logger = logging.getLogger(__name__)


def _normalize_mode(mode: str | None) -> str:
    if not mode:
        return "manage"
    value = str(mode).strip().lower()
    if value in {"view", "viewer", "readonly"}:
        return "view"
    return "manage"


def _hidden_desktop_enabled() -> bool:
    value = os.getenv("RC_ENABLE_HIDDEN_DESKTOP", "0")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_session_resources(mode: str | None) -> SessionResources:
    normalized = _normalize_mode(mode)
    if normalized == "view":
        controller = NullInputController()
        screen_track = ScreenTrack()
        control_handler = ControlHandler(controller)
        return SessionResources(control_handler, [screen_track, AudioTrack()])

    if platform.system() == "Windows" and _hidden_desktop_enabled():
        try:
            from remote_client.windows.hidden_desktop import HiddenDesktopSession
        except Exception as exc:
            logger.warning("Hidden desktop unavailable, falling back: %s", exc)
        else:
            try:
                session = HiddenDesktopSession()
            except Exception as exc:
                logger.warning("Hidden desktop init failed, falling back: %s", exc)
            else:
                control_handler = ControlHandler(session.input_controller)
                media_tracks: list[Any] = [session.screen_track, AudioTrack()]
                return SessionResources(
                    control_handler,
                    media_tracks,
                    close=session.close,
                    launch_app=session.launch_application,
                )

    controller = InputController()
    screen_track = ScreenTrack(draw_cursor=False)
    control_handler = ControlHandler(controller)
    return SessionResources(control_handler, [screen_track, AudioTrack()])
