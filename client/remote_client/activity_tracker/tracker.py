"""Keyboard input and clipboard tracker for Windows.

Captures only printable characters and clipboard paste operations.
"""
from __future__ import annotations

import ctypes
import logging
import platform
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Set, Optional

logger = logging.getLogger(__name__)

# Windows API constants - only essential keys
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt key
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_V = 0x56
CF_UNICODETEXT = 13


class KeyboardLayoutHelper:
    """Helper class to convert virtual key codes to actual characters with keyboard layout support."""
    
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._user32 = None
        if self._is_windows:
            try:
                self._user32 = ctypes.windll.user32
            except Exception as e:
                logger.debug("Failed to load user32.dll: %s", e)
    
    def vk_to_char(self, vk_code: int, scan_code: int = 0) -> Optional[str]:
        """Convert virtual key code to character using current keyboard layout.
        
        Args:
            vk_code: Virtual key code
            scan_code: Hardware scan code (optional)
            
        Returns:
            The character string or None if not a printable character
        """
        if not self._is_windows or not self._user32:
            return None
        
        try:
            # Get current thread's keyboard layout
            hwnd = self._user32.GetForegroundWindow()
            thread_id = self._user32.GetWindowThreadProcessId(hwnd, None)
            hkl = self._user32.GetKeyboardLayout(thread_id)
            
            # Get keyboard state
            keyboard_state = (ctypes.c_ubyte * 256)()
            if not self._user32.GetKeyboardState(keyboard_state):
                return None
            
            # Convert virtual key to unicode character
            char_buffer = (ctypes.c_wchar * 5)()
            
            # Use scan code if provided, otherwise get it from virtual key
            if scan_code == 0:
                scan_code = self._user32.MapVirtualKeyExW(vk_code, 0, hkl)
            
            result = self._user32.ToUnicodeEx(
                vk_code,
                scan_code,
                keyboard_state,
                char_buffer,
                len(char_buffer),
                0,  # flags
                hkl
            )
            
            if result > 0:
                return char_buffer.value[:result]
            elif result < 0:
                # Dead key - call again to clear the state
                self._user32.ToUnicodeEx(
                    vk_code, scan_code, keyboard_state,
                    char_buffer, len(char_buffer), 0, hkl
                )
                return None
            
            return None
            
        except Exception as e:
            logger.debug("VK to char conversion error: %s", e)
            return None
    
    def get_clipboard_text(self) -> Optional[str]:
        """Get text from clipboard using Windows API."""
        if not self._is_windows:
            return None
        
        # Try win32clipboard first (most reliable)
        try:
            import win32clipboard
            import win32con
            
            for _ in range(3):
                try:
                    win32clipboard.OpenClipboard()
                    try:
                        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                            if data:
                                return data
                    finally:
                        win32clipboard.CloseClipboard()
                    break
                except Exception:
                    time.sleep(0.05)
        except ImportError:
            pass
        except Exception:
            pass
        
        # Fallback to ctypes
        if not self._user32:
            return None
        
        kernel32 = ctypes.windll.kernel32
        
        for _ in range(3):
            try:
                if not self._user32.OpenClipboard(None):
                    time.sleep(0.05)
                    continue
                
                try:
                    handle = self._user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        break
                    
                    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                    kernel32.GlobalLock.restype = ctypes.c_void_p
                    
                    data_ptr = kernel32.GlobalLock(handle)
                    if not data_ptr:
                        break
                    
                    try:
                        return ctypes.wstring_at(data_ptr)
                    finally:
                        kernel32.GlobalUnlock(handle)
                finally:
                    self._user32.CloseClipboard()
            except Exception:
                time.sleep(0.05)
        
        return None
    
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
    """Track keyboard input and clipboard with application context.
    
    Only captures printable characters and clipboard paste operations.
    """

    # Only essential special keys for text input
    SPECIAL_KEYS = {
        "space": " ",
        "enter": "\n",
        "tab": "\t",
        "backspace": "",  # Ignored - just indicates deletion
        # Modifiers - ignored when pressed alone
        "shift": "",
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
    }

    # VK codes for essential input keys only
    VK_SPECIAL_KEYS = {
        VK_TAB: "\t",
        VK_RETURN: "\n",
        VK_SPACE: " ",
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
        self._keyboard_helper = KeyboardLayoutHelper()
        self._buffer = InputBuffer()
        self._buffer_lock = threading.Lock()
        self._activity_queue: queue.Queue[ActivityEntry] = queue.Queue()
        self._listener = None
        self._flush_thread: threading.Thread | None = None
        self._running = False
        # Track pressed modifier keys
        self._pressed_modifiers: Set[str] = set()
        self._ctrl_pressed = False

    def start(self) -> None:
        """Start tracking keyboard input and clipboard paste (Ctrl+V)."""
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
        """Handle key press event with proper keyboard layout support."""
        try:
            key_name = None
            key_char = None
            vk_code = None
            scan_code = 0
            
            # Extract key information from pynput key object
            if hasattr(key, "name") and key.name:
                key_name = key.name.lower()
            if hasattr(key, "char") and key.char:
                key_char = key.char
            if hasattr(key, "vk") and key.vk:
                vk_code = key.vk
            if hasattr(key, "_scan"):
                scan_code = key._scan or 0
            
            # Track Ctrl key state
            if key_name in ("ctrl_l", "ctrl_r", "ctrl") or vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
                self._ctrl_pressed = True
                self._pressed_modifiers.add("ctrl")
                return
            
            # Track Shift key state
            if key_name in ("shift_l", "shift_r", "shift") or vk_code in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
                self._pressed_modifiers.add("shift")
                return
            
            # Track Alt key state
            if key_name in ("alt_l", "alt_r", "alt_gr", "alt") or vk_code in (VK_MENU, VK_LMENU, VK_RMENU):
                self._pressed_modifiers.add("alt")
                return
            
            # Check for Ctrl+V (paste from clipboard)
            if self._ctrl_pressed:
                is_paste = (
                    vk_code == VK_V or
                    (key_char and (key_char.lower() == "v" or key_char == "\x16")) or
                    (key_name and key_name == "v")
                )
                if is_paste:
                    self._handle_paste()
                return  # Ignore all Ctrl+key combinations
            
            # Handle Backspace - remove last character from buffer
            if key_name == "backspace" or vk_code == VK_BACK:
                with self._buffer_lock:
                    if self._buffer.text:
                        self._buffer.text = self._buffer.text[:-1]
                        self._buffer.last_updated = time.time()
                return
            
            char = None
            
            # Use pynput's char first - it already handles Shift for uppercase
            if key_char is not None:
                if ord(key_char) >= 32:  # Printable character
                    char = key_char
            
            # Handle special keys (Space, Enter, Tab)
            if char is None and vk_code is not None:
                if vk_code in self.VK_SPECIAL_KEYS:
                    char = self.VK_SPECIAL_KEYS[vk_code]

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
            key_name = None
            vk_code = None
            
            if hasattr(key, "name") and key.name:
                key_name = key.name.lower()
            if hasattr(key, "vk") and key.vk:
                vk_code = key.vk
            
            # Release Ctrl (check all possible VK codes)
            if key_name in ("ctrl_l", "ctrl_r", "ctrl") or vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
                self._ctrl_pressed = False
                self._pressed_modifiers.discard("ctrl")
            # Release Shift
            elif key_name in ("shift_l", "shift_r", "shift") or vk_code in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
                self._pressed_modifiers.discard("shift")
            # Release Alt
            elif key_name in ("alt_l", "alt_r", "alt_gr", "alt") or vk_code in (VK_MENU, VK_LMENU, VK_RMENU):
                self._pressed_modifiers.discard("alt")
        except Exception:
            pass
    
    def _handle_paste(self) -> None:
        """Handle paste operation (Ctrl+V) - record clipboard content."""
        if platform.system() != "Windows":
            return
        
        try:
            time.sleep(0.05)  # Let paste complete in target app
            pasted_text = self._keyboard_helper.get_clipboard_text()
            
            # Fallback to pyperclip
            if not pasted_text:
                try:
                    import pyperclip
                    pasted_text = pyperclip.paste()
                except Exception:
                    pass
            
            if not pasted_text:
                return
            
            app_name, window_title = self._window_info.get_active_window_info()
            
            with self._buffer_lock:
                if (
                    self._buffer.application != app_name
                    or self._buffer.window_title != window_title
                ):
                    self._flush_buffer_locked()
                    self._buffer.application = app_name
                    self._buffer.window_title = window_title
                    self._buffer.started_at = datetime.now(timezone.utc).isoformat()
                
                self._buffer.text += f"[PASTE]{pasted_text}[/PASTE]"
                self._buffer.last_updated = time.time()
                
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