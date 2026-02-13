"""
App-Bound Encryption (ABE) module for Brave browser cookie decryption.

Brave is based on Chromium and uses the same App-Bound Encryption mechanism
as Chrome 127+. This module provides Brave-specific methods using the unified
ABE native module.

Key differences from Chrome:
1. Brave stores data in %LOCALAPPDATA%/BraveSoftware/Brave-Browser/User Data/
2. Brave has its own elevation service with Brave-specific CLSIDs
3. Brave has additional privacy features that may affect cookie handling

References:
- Chrome ABE: https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- xaitax's ABE research: https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional, Dict, List

from .errors import CookieExportError
from .app_bound_encryption import (
    is_abe_encrypted_key,
    is_abe_encrypted_value,
    decrypt_abe_key,
    decrypt_abe_value,
    AppBoundDecryptor,
    CDPCookieExtractor,
    BrowserType,
    ABE_PREFIX,
    V20_PREFIX,
    AES_GCM_NONCE_LENGTH,
    AES_GCM_TAG_LENGTH,
    DPAPI_PREFIX,
)

logger = logging.getLogger(__name__)


class BraveAppBoundDecryptionError(CookieExportError):
    """Raised when Brave App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("brave_abe_decryption_failed", message)


def _get_brave_exe_path() -> Optional[Path]:
    """Find Brave browser executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
    try:
        import winreg
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\BraveSoftware\Brave-Browser") as key:
                    install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if install_path:
                        brave_exe = Path(install_path) / "brave.exe"
                        if brave_exe.exists():
                            return brave_exe
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    return None


def _get_brave_user_data_dir() -> Optional[Path]:
    """Get Brave User Data directory."""
    if os.name != "nt":
        return None
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        path = Path(local_app_data) / "BraveSoftware" / "Brave-Browser" / "User Data"
        if path.exists():
            return path
    return None


def _get_brave_local_state_path() -> Optional[Path]:
    """Get Brave Local State file path."""
    user_data_dir = _get_brave_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_brave_elevation_service_path() -> Optional[Path]:
    """Find Brave Elevation Service executable."""
    brave_path = _get_brave_exe_path()
    if not brave_path:
        return None
    
    brave_app_dir = brave_path.parent
    
    try:
        for item in brave_app_dir.iterdir():
            if item.is_dir() and item.name[0].isdigit():
                elevation_service = item / "elevation_service.exe"
                if elevation_service.exists():
                    return elevation_service
    except Exception:
        pass
    
    elevation_service = brave_app_dir / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    
    return None


def _is_brave_elevation_service_running() -> bool:
    """Check if Brave Elevation Service is running."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["sc", "query", "BraveElevationService"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "RUNNING" in result.stdout
    except Exception:
        return False


def _start_brave_elevation_service() -> bool:
    """Try to start Brave Elevation Service."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["net", "start", "BraveElevationService"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 or "already been started" in result.stderr
    except Exception:
        return False


def load_brave_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """
    Load and decrypt Brave's ABE key from Local State.
    
    Uses the unified ABE native module for decryption.
    """
    if local_state_path is None:
        local_state_path = _get_brave_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Brave Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Brave Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        # Remove DPAPI prefix if present
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # Use Brave-specific browser type
            return decrypt_abe_key(encrypted_key, BrowserType.BRAVE, auto_detect=True)
        else:
            # Not ABE, try DPAPI
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load Brave ABE key: {e}")
        return None


def _dpapi_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """Decrypt data using Windows DPAPI."""
    if os.name != "nt":
        return None
    try:
        import win32crypt
        return win32crypt.CryptUnprotectData(encrypted_data, None, None, None, 0)[1]
    except ImportError:
        logger.debug("win32crypt not available")
    except Exception as e:
        logger.debug(f"DPAPI decryption failed: {e}")
    return None


def decrypt_brave_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Brave cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise BraveAppBoundDecryptionError("Decryption failed")
    return result


class BraveAppBoundDecryptor(AppBoundDecryptor):
    """
    High-level interface for Brave App-Bound Encryption decryption.
    
    Extends the base AppBoundDecryptor with Brave-specific functionality.
    """
    
    def __init__(self, local_state_path: Optional[Path] = None):
        """
        Initialize Brave ABE decryptor.
        
        Args:
            local_state_path: Path to Local State file (auto-detected if None)
        """
        if local_state_path is None:
            local_state_path = _get_brave_local_state_path()
        super().__init__(local_state_path, BrowserType.BRAVE)
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of ABE key using Brave-specific loading."""
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_brave_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("Brave ABE decryptor initialized successfully")
        else:
            logger.warning("Brave ABE decryptor initialization failed")


def get_brave_cookies_via_cdp() -> List[Dict[str, Any]]:
    """
    Get decrypted Brave cookies using Chrome DevTools Protocol.
    
    Returns:
        List of cookie dictionaries
    """
    brave_path = _get_brave_exe_path()
    if not brave_path:
        logger.warning("Brave executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_brave_user_data_dir()
    
    try:
        with CDPCookieExtractor(brave_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"Brave CDP extraction failed: {e}")
        return []


def _get_brave_version() -> Optional[str]:
    """Get Brave version from registry or files."""
    if os.name != "nt":
        return None
    
    try:
        import winreg
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\BraveSoftware\Brave-Browser\BLBeacon") as key:
                    version, _ = winreg.QueryValueEx(key, "version")
                    if version:
                        return version
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    local_state = _get_brave_local_state_path()
    if local_state and local_state.exists():
        try:
            raw = local_state.read_text(encoding="utf-8")
            data = json.loads(raw)
            if "browser" in data:
                browser_info = data["browser"]
                if isinstance(browser_info, dict):
                    version = browser_info.get("last_known_version")
                    if version:
                        return version
        except Exception:
            pass
    
    return None


def check_brave_abe_support() -> Dict[str, Any]:
    """Check system support for Brave App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    # Get base ABE support info
    result = check_abe_support()
    
    # Add Brave-specific info
    result["brave_installed"] = False
    result["brave_path"] = None
    result["brave_user_data_dir"] = None
    result["brave_elevation_service"] = False
    result["brave_elevation_service_path"] = None
    result["brave_elevation_service_running"] = False
    result["brave_version"] = None
    
    brave_path = _get_brave_exe_path()
    result["brave_installed"] = brave_path is not None
    if brave_path:
        result["brave_path"] = str(brave_path)
    
    user_data_dir = _get_brave_user_data_dir()
    if user_data_dir:
        result["brave_user_data_dir"] = str(user_data_dir)
    
    if brave_path:
        elevation_service = _get_brave_elevation_service_path()
        result["brave_elevation_service"] = elevation_service is not None
        if elevation_service:
            result["brave_elevation_service_path"] = str(elevation_service)
    
    result["brave_elevation_service_running"] = _is_brave_elevation_service_running()
    result["brave_version"] = _get_brave_version()
    
    return result


# Export public API
__all__ = [
    # Classes
    "BraveAppBoundDecryptionError",
    "BraveAppBoundDecryptor",
    # Functions
    "load_brave_abe_key_from_local_state",
    "decrypt_brave_v20_value",
    "get_brave_cookies_via_cdp",
    "check_brave_abe_support",
    # Re-exports from main module
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
