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

_CURSOR_MODE_OVERRIDE: str | None = None
_LAST_HIDDEN_DESKTOP_ERROR: str | None = None


def set_cursor_mode_override(value: str | None) -> None:
    global _CURSOR_MODE_OVERRIDE
    if value is None:
        _CURSOR_MODE_OVERRIDE = None
        return
    cleaned = str(value).strip().lower()
    _CURSOR_MODE_OVERRIDE = cleaned or None


def _set_hidden_desktop_error(reason: str | None) -> None:
    global _LAST_HIDDEN_DESKTOP_ERROR
    _LAST_HIDDEN_DESKTOP_ERROR = reason


def get_last_hidden_desktop_error() -> str | None:
    return _LAST_HIDDEN_DESKTOP_ERROR


def _normalize_mode(mode: str | None) -> str:
    if not mode:
        return "manage"
    value = str(mode).strip().lower()
    if value in {"view", "viewer", "readonly"}:
        return "view"
    return "manage"


def _hidden_desktop_enabled() -> bool:
    override = _CURSOR_MODE_OVERRIDE
    if override in {"independent", "hidden", "hidden_desktop"}:
        return True
    if override in {"shared", "visible", "normal", "desktop"}:
        return False
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
    _set_hidden_desktop_error(None)
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
            get_status=lambda: {
                "hidden_desktop": False,
                "hidden_error": get_last_hidden_desktop_error(),
            },
        )

    if platform.system() == "Windows" and _hidden_desktop_enabled():
        try:
            from remote_client.windows.hidden_desktop import HiddenDesktopSession
        except Exception as exc:
            reason = f"Hidden desktop unavailable: {exc}"
            _set_hidden_desktop_error(reason)
            logger.warning("%s", reason)
        else:
            try:
                session = HiddenDesktopSession()
            except Exception as exc:
                reason = f"Hidden desktop init failed: {exc}"
                _set_hidden_desktop_error(reason)
                logger.warning("%s", reason)
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
                    get_status=lambda: {
                        "hidden_desktop": True,
                        "hidden_error": session.get_capture_error() or get_last_hidden_desktop_error(),
                    },
                )
    else:
        if platform.system() != "Windows":
            _set_hidden_desktop_error("Hidden desktop is only supported on Windows.")
        elif not _hidden_desktop_enabled():
            _set_hidden_desktop_error("Hidden desktop disabled by configuration.")

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
        get_status=lambda: {
            "hidden_desktop": False,
            "hidden_error": get_last_hidden_desktop_error(),
        },
    )
