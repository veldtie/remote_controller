"""
App-Bound Encryption (ABE) module for Linken Sphere 2 (Sfera2) browser cookie decryption.

Linken Sphere 2 is a Chromium-based antidetect browser that uses the same
App-Bound Encryption mechanism as Chrome 127+. This module provides
Linken Sphere-specific methods using the unified ABE native module.

Key differences:
1. Linken Sphere stores data in %LOCALAPPDATA%/Linken Sphere 2/ or %APPDATA%/
2. Linken Sphere uses Chrome's elevation service mechanism
3. Linken Sphere has multiple session directories for different browser sessions
4. Sessions may be encrypted or stored in separate containers

References:
- Chrome ABE: https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- xaitax's ABE research: https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption
"""
from __future__ import annotations

import base64
import json
import logging
import os
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


class LinkenSphereAppBoundDecryptionError(CookieExportError):
    """Raised when Linken Sphere App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("linken_sphere_abe_decryption_failed", message)


# Aliases for Sfera2
Sfera2AppBoundDecryptionError = LinkenSphereAppBoundDecryptionError


def _get_linken_sphere_exe_path() -> Optional[Path]:
    """Find Linken Sphere 2 executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        # Linken Sphere 2
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere 2" / "sphere.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere 2" / "Application" / "sphere.exe",
        Path(os.environ.get("APPDATA", "")) / "Linken Sphere 2" / "sphere.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Linken Sphere 2" / "sphere.exe",
        # Legacy Linken Sphere
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere" / "sphere.exe",
        Path(os.environ.get("APPDATA", "")) / "Linken Sphere" / "sphere.exe",
        # Alternative names
        Path(os.environ.get("LOCALAPPDATA", "")) / "Sphere" / "sphere.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "LS" / "sphere.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
    try:
        import winreg
        registry_keys = [
            r"SOFTWARE\Linken Sphere 2",
            r"SOFTWARE\Linken Sphere",
            r"SOFTWARE\Tenebris",  # Linken Sphere developer
        ]
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for key_path in registry_keys:
                try:
                    with winreg.OpenKey(hkey, key_path) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_path:
                            exe = Path(install_path) / "sphere.exe"
                            if exe.exists():
                                return exe
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    
    return None


def _get_linken_sphere_user_data_dir() -> Optional[Path]:
    """Get Linken Sphere 2 User Data directory."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere 2" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "Linken Sphere 2" / "User Data",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "Linken Sphere" / "User Data",
        # Sessions directory (for individual browser sessions)
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere 2" / "sessions",
        Path(os.environ.get("APPDATA", "")) / "Linken Sphere 2" / "sessions",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_linken_sphere_sessions_dir() -> Optional[Path]:
    """Get Linken Sphere 2 sessions directory (contains individual browser profiles)."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere 2" / "sessions",
        Path(os.environ.get("APPDATA", "")) / "Linken Sphere 2" / "sessions",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Linken Sphere" / "sessions",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_linken_sphere_local_state_path() -> Optional[Path]:
    """Get Linken Sphere 2 Local State file path."""
    user_data_dir = _get_linken_sphere_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_linken_sphere_sessions() -> List[Path]:
    """Get all Linken Sphere 2 session directories."""
    sessions = []
    
    # Check main User Data dir
    user_data_dir = _get_linken_sphere_user_data_dir()
    if user_data_dir and user_data_dir.exists():
        try:
            for item in user_data_dir.iterdir():
                if item.is_dir():
                    if item.name == "Default" or item.name.startswith("Profile "):
                        sessions.append(item)
        except Exception:
            pass
    
    # Check sessions directory
    sessions_dir = _get_linken_sphere_sessions_dir()
    if sessions_dir and sessions_dir.exists():
        try:
            for item in sessions_dir.iterdir():
                if item.is_dir():
                    # Linken Sphere sessions are typically UUID-like directories
                    user_data = item / "User Data"
                    if user_data.exists():
                        default_profile = user_data / "Default"
                        if default_profile.exists():
                            sessions.append(default_profile)
        except Exception:
            pass
    
    return sessions


def load_linken_sphere_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """Load and decrypt Linken Sphere 2's ABE key from Local State."""
    if local_state_path is None:
        local_state_path = _get_linken_sphere_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Linken Sphere 2 Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Linken Sphere Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # Linken Sphere uses Chrome mechanism
            return decrypt_abe_key(encrypted_key, BrowserType.CHROME, auto_detect=True)
        else:
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load Linken Sphere ABE key: {e}")
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


def decrypt_linken_sphere_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Linken Sphere cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise LinkenSphereAppBoundDecryptionError("Decryption failed")
    return result


# Alias for Sfera2
decrypt_sfera2_v20_value = decrypt_linken_sphere_v20_value


class LinkenSphereAppBoundDecryptor(AppBoundDecryptor):
    """High-level interface for Linken Sphere 2 App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        if local_state_path is None:
            local_state_path = _get_linken_sphere_local_state_path()
        # Linken Sphere uses Chrome's mechanism
        super().__init__(local_state_path, BrowserType.CHROME)
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_linken_sphere_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("Linken Sphere 2 ABE decryptor initialized successfully")
        else:
            logger.warning("Linken Sphere 2 ABE decryptor initialization failed")


# Alias for Sfera2
Sfera2AppBoundDecryptor = LinkenSphereAppBoundDecryptor


def get_linken_sphere_cookies_via_cdp() -> List[Dict[str, Any]]:
    """Get decrypted Linken Sphere 2 cookies using Chrome DevTools Protocol."""
    sphere_path = _get_linken_sphere_exe_path()
    if not sphere_path:
        logger.warning("Linken Sphere 2 executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_linken_sphere_user_data_dir()
    
    try:
        with CDPCookieExtractor(sphere_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"Linken Sphere 2 CDP extraction failed: {e}")
        return []


# Alias for Sfera2
get_sfera2_cookies_via_cdp = get_linken_sphere_cookies_via_cdp


def check_linken_sphere_abe_support() -> Dict[str, Any]:
    """Check system support for Linken Sphere 2 App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    result = check_abe_support()
    
    result["linken_sphere_installed"] = False
    result["linken_sphere_path"] = None
    result["linken_sphere_user_data_dir"] = None
    result["linken_sphere_sessions_dir"] = None
    result["linken_sphere_sessions"] = []
    
    sphere_path = _get_linken_sphere_exe_path()
    result["linken_sphere_installed"] = sphere_path is not None
    if sphere_path:
        result["linken_sphere_path"] = str(sphere_path)
    
    user_data_dir = _get_linken_sphere_user_data_dir()
    if user_data_dir:
        result["linken_sphere_user_data_dir"] = str(user_data_dir)
    
    sessions_dir = _get_linken_sphere_sessions_dir()
    if sessions_dir:
        result["linken_sphere_sessions_dir"] = str(sessions_dir)
    
    sessions = _get_linken_sphere_sessions()
    result["linken_sphere_sessions"] = [str(s) for s in sessions]
    
    return result


# Alias for Sfera2
check_sfera2_abe_support = check_linken_sphere_abe_support


__all__ = [
    # Linken Sphere exports
    "LinkenSphereAppBoundDecryptionError",
    "LinkenSphereAppBoundDecryptor",
    "load_linken_sphere_abe_key_from_local_state",
    "decrypt_linken_sphere_v20_value",
    "get_linken_sphere_cookies_via_cdp",
    "check_linken_sphere_abe_support",
    # Sfera2 aliases
    "Sfera2AppBoundDecryptionError",
    "Sfera2AppBoundDecryptor",
    "decrypt_sfera2_v20_value",
    "get_sfera2_cookies_via_cdp",
    "check_sfera2_abe_support",
    # Re-exports
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
