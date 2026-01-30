"""Session resource factory for remote connections."""
from __future__ import annotations

from typing import Any, Callable

import logging
import os
import platform

from remote_client.control.cursor_visibility import CursorVisibilityController
from remote_client.control.handlers import ControlHandler, StabilizedControlHandler
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


def _input_stabilizer_enabled() -> bool:
    value = os.getenv("RC_INPUT_STABILIZER", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _build_control_handler(controller: InputController) -> ControlHandler:
    if _input_stabilizer_enabled():
        return StabilizedControlHandler(controller)
    return ControlHandler(controller)


def _compose_close(
    primary: Callable[[], None] | None,
    cursor_controller: CursorVisibilityController | None,
) -> Callable[[], None] | None:
    if not primary and not cursor_controller:
        return None

    def _close() -> None:
        if cursor_controller:
            cursor_controller.reset()
        if primary:
            primary()

    return _close


def build_session_resources(mode: str | None) -> SessionResources:
    normalized = _normalize_mode(mode)
    cursor_controller = CursorVisibilityController()
    if normalized == "view":
        controller = NullInputController()
        screen_track = ScreenTrack()
        control_handler = ControlHandler(controller)
        media_tracks: list[Any] = [screen_track, AudioTrack()]

        def _set_stream_profile(
            profile: str | None,
            width: int | None,
            height: int | None,
            fps: int | None,
        ) -> None:
            for track in media_tracks:
                if hasattr(track, "set_profile"):
                    track.set_profile(profile, width, height, fps)

        return SessionResources(
            control_handler,
            media_tracks,
            close=_compose_close(None, cursor_controller),
            set_stream_profile=_set_stream_profile,
            set_cursor_visibility=cursor_controller.set_visible,
        )

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

                def _set_stream_profile(
                    profile: str | None,
                    width: int | None,
                    height: int | None,
                    fps: int | None,
                ) -> None:
                    for track in media_tracks:
                        if hasattr(track, "set_profile"):
                            track.set_profile(profile, width, height, fps)

                return SessionResources(
                    control_handler,
                    media_tracks,
                    close=_compose_close(session.close, cursor_controller),
                    launch_app=session.launch_application,
                    set_stream_profile=_set_stream_profile,
                    set_cursor_visibility=cursor_controller.set_visible,
                )

    controller = InputController()
    screen_track = ScreenTrack(draw_cursor=False)
    control_handler = _build_control_handler(controller)
    media_tracks: list[Any] = [screen_track, AudioTrack()]

    def _set_stream_profile(
        profile: str | None,
        width: int | None,
        height: int | None,
        fps: int | None,
    ) -> None:
        for track in media_tracks:
            if hasattr(track, "set_profile"):
                track.set_profile(profile, width, height, fps)

    return SessionResources(
        control_handler,
        media_tracks,
        close=_compose_close(None, cursor_controller),
        set_stream_profile=_set_stream_profile,
        set_cursor_visibility=cursor_controller.set_visible,
    )
