"""Keyboard input and clipboard paste tracker for Windows."""
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

# Windows API constants for keyboard
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt key
VK_CAPITAL = 0x14
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_DELETE = 0x2E
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_HOME = 0x24
VK_END = 0x23
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22   # Page Down
VK_INSERT = 0x2D
VK_SNAPSHOT = 0x2C  # Print Screen
VK_SCROLL = 0x91
VK_PAUSE = 0x13
VK_NUMLOCK = 0x90
VK_F1 = 0x70
VK_F12 = 0x7B
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4  # Left Alt
VK_RMENU = 0xA5  # Right Alt
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
        """Get text from clipboard using Windows API.
        
        Prioritizes win32clipboard (pywin32) as it's more reliable,
        falls back to raw ctypes if needed.
        """
        if not self._is_windows:
            logger.info("get_clipboard_text: Not Windows")
            return None
        
        import time
        
        # Method 1: Try win32clipboard first (most reliable on Windows)
        try:
            import win32clipboard
            import win32con
            
            for attempt in range(3):
                try:
                    win32clipboard.OpenClipboard()
                    try:
                        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                            if data:
                                logger.info("win32clipboard success: len=%d", len(data))
                                return data
                        else:
                            # Check what formats ARE available
                            formats = []
                            fmt = 0
                            while True:
                                fmt = win32clipboard.EnumClipboardFormats(fmt)
                                if fmt == 0:
                                    break
                                formats.append(fmt)
                            logger.info("win32clipboard: CF_UNICODETEXT not available, formats=%s", formats[:10])
                    finally:
                        win32clipboard.CloseClipboard()
                    break
                except Exception as e:
                    logger.info("win32clipboard attempt %d failed: %s", attempt + 1, e)
                    if attempt < 2:
                        time.sleep(0.05)
                        continue
        except ImportError:
            logger.info("win32clipboard not available, trying ctypes")
        except Exception as e:
            logger.info("win32clipboard error: %s", e)
        
        # Method 2: Try raw ctypes as fallback
        if not self._user32:
            logger.info("get_clipboard_text: no user32 for ctypes fallback")
            return None
        
        kernel32 = ctypes.windll.kernel32
        max_retries = 5
        retry_delay = 0.05
        last_error_code = 0
        
        for attempt in range(max_retries):
            try:
                result = self._user32.OpenClipboard(None)
                if not result:
                    last_error_code = kernel32.GetLastError()
                    logger.info(
                        "ctypes OpenClipboard failed (attempt %d/%d), error=%d",
                        attempt + 1, max_retries, last_error_code
                    )
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    break
                
                try:
                    handle = self._user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        format_count = self._user32.CountClipboardFormats()
                        logger.info(
                            "ctypes GetClipboardData returned NULL, formats=%d",
                            format_count
                        )
                        break
                    
                    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                    kernel32.GlobalLock.restype = ctypes.c_void_p
                    
                    data_ptr = kernel32.GlobalLock(handle)
                    if not data_ptr:
                        last_error_code = kernel32.GetLastError()
                        logger.info("ctypes GlobalLock failed, error=%d", last_error_code)
                        break
                    
                    try:
                        text = ctypes.wstring_at(data_ptr)
                        logger.info("ctypes clipboard success: len=%d", len(text) if text else 0)
                        return text
                    finally:
                        kernel32.GlobalUnlock(handle)
                        
                finally:
                    self._user32.CloseClipboard()
                    
            except Exception as e:
                logger.info("ctypes clipboard error (attempt %d): %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                break
        
        logger.warning("All clipboard read methods failed (last_error=%d)", last_error_code)
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

    # Map VK codes to special key names for display
    VK_SPECIAL_KEYS = {
        VK_BACK: "[BACKSPACE]",
        VK_TAB: "[TAB]",
        VK_RETURN: "[ENTER]\n",
        VK_ESCAPE: "[ESC]",
        VK_SPACE: " ",
        VK_DELETE: "[DELETE]",
        VK_LEFT: "[LEFT]",
        VK_UP: "[UP]",
        VK_RIGHT: "[RIGHT]",
        VK_DOWN: "[DOWN]",
        VK_HOME: "[HOME]",
        VK_END: "[END]",
        VK_PRIOR: "[PGUP]",
        VK_NEXT: "[PGDN]",
        VK_INSERT: "[INS]",
        VK_SNAPSHOT: "[PRTSC]",
        VK_SCROLL: "[SCRLK]",
        VK_PAUSE: "[PAUSE]",
        VK_NUMLOCK: "[NUMLK]",
        VK_CAPITAL: "[CAPS]",
    }
    # Add F1-F12 keys
    for i in range(12):
        VK_SPECIAL_KEYS[VK_F1 + i] = f"[F{i+1}]"

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
            
            # Debug logging for key press (helps diagnose Ctrl+V issues)
            # Log Ctrl, V and control characters at INFO level for diagnosis
            if key_name in ("ctrl_l", "ctrl_r", "ctrl") or vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL) or \
               (key_char and (key_char.lower() == 'v' or key_char == '\x16')) or vk_code == VK_V:
                logger.info(
                    "KEY: name=%r, char=%r, vk=%s, scan=%s, ctrl_pressed=%s",
                    key_name, key_char, vk_code, scan_code, self._ctrl_pressed
                )
            
            # Track Ctrl key state (check all possible VK codes)
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
                # Check by VK code, by character 'v', or by control character '\x16'
                is_paste = False
                if vk_code == VK_V:  # 0x56
                    is_paste = True
                elif key_char:
                    if key_char.lower() == "v" or key_char == "\x16":
                        is_paste = True
                elif key_name and key_name == "v":
                    is_paste = True
                
                if is_paste:
                    logger.debug("Ctrl+V detected (vk=%s, char=%r, name=%s)", vk_code, key_char, key_name)
                    self._handle_paste()
                    return
                # Ignore other Ctrl+key combinations
                return
            
            char = None
            
            # First, try to get the character using Windows API with proper keyboard layout
            if vk_code is not None and platform.system() == "Windows":
                # Check if it's a special key first
                if vk_code in self.VK_SPECIAL_KEYS:
                    char = self.VK_SPECIAL_KEYS[vk_code]
                else:
                    # Try to convert VK code to character with current keyboard layout
                    layout_char = self._keyboard_helper.vk_to_char(vk_code, scan_code)
                    if layout_char and len(layout_char) > 0:
                        char = layout_char
            
            # Fallback: use pynput's character (may not respect keyboard layout)
            if char is None:
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
        """Handle paste operation (Ctrl+V) - record clipboard content as pasted text."""
        logger.info("_handle_paste called")
        
        if platform.system() != "Windows":
            logger.debug("Not Windows, skipping paste")
            return
        
        try:
            # Small delay to let the paste operation complete in the target app
            time.sleep(0.05)
            
            # Use keyboard helper to get clipboard text
            pasted_text = self._keyboard_helper.get_clipboard_text()
            
            if pasted_text:
                logger.info(
                    "Clipboard text read successfully: len=%d, preview=%r",
                    len(pasted_text), pasted_text[:50] if len(pasted_text) > 50 else pasted_text
                )
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
                    
                logger.info("Paste recorded: %d chars to window: %s", len(pasted_text), window_title[:50] if window_title else "Unknown")
            else:
                # Try alternative method - use pyperclip if available
                try:
                    import pyperclip
                    pasted_text = pyperclip.paste()
                    if pasted_text:
                        logger.info("Clipboard read via pyperclip: len=%d", len(pasted_text))
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
                        logger.info("Paste recorded via pyperclip: %d chars", len(pasted_text))
                        return
                except ImportError:
                    pass
                except Exception as e:
                    logger.debug("pyperclip fallback failed: %s", e)
                
                logger.warning("Clipboard was empty or failed to read (tried Windows API and pyperclip)")
        except Exception as e:
            logger.exception("Paste handling error: %s", e)

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