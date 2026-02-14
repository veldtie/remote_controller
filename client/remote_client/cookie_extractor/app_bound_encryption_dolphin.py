"""
App-Bound Encryption (ABE) module for Dolphin Anty browser cookie decryption.

Dolphin Anty is a Chromium-based antidetect browser that uses the same
App-Bound Encryption mechanism as Chrome 127+. This module provides
Dolphin-specific methods using the unified ABE native module.

Key differences from Chrome:
1. Dolphin stores data in %LOCALAPPDATA%/Dolphin Anty/ or %APPDATA%/Dolphin Anty/
2. Dolphin uses Chrome's elevation service mechanism
3. Dolphin has multiple browser profile directories for different browser profiles
4. Each profile may have its own User Data directory with unique Local State

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


class DolphinAppBoundDecryptionError(CookieExportError):
    """Raised when Dolphin Anty App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("dolphin_abe_decryption_failed", message)


# Alias for DolphinAnty
DolphinAntyAppBoundDecryptionError = DolphinAppBoundDecryptionError


def _get_dolphin_exe_path() -> Optional[Path]:
    """Find Dolphin Anty browser executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        # Dolphin Anty (primary)
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "Application" / "Dolphin Anty.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        # Legacy Dolphin paths
        Path(os.environ.get("PROGRAMFILES", "")) / "Dolphin" / "dolphin.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Dolphin" / "dolphin.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin" / "dolphin.exe",
        Path(os.environ.get("APPDATA", "")) / "Dolphin" / "dolphin.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
    try:
        import winreg
        registry_keys = [
            r"SOFTWARE\Dolphin Anty",
            r"SOFTWARE\Dolphin",
        ]
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for key_path in registry_keys:
                try:
                    with winreg.OpenKey(hkey, key_path) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_path:
                            for exe_name in ["Dolphin Anty.exe", "dolphin.exe"]:
                                exe = Path(install_path) / exe_name
                                if exe.exists():
                                    return exe
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    
    return None


def _get_dolphin_user_data_dir() -> Optional[Path]:
    """Get Dolphin Anty User Data directory."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        # Dolphin Anty (primary)
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "User Data",
        # Legacy Dolphin
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "Dolphin" / "User Data",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_dolphin_browser_profiles_dir() -> Optional[Path]:
    """Get Dolphin Anty browser profiles directory (for individual profiles)."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "browser_profiles",
        Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "browser_profiles",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "profiles",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_dolphin_local_state_path() -> Optional[Path]:
    """Get Dolphin Anty Local State file path."""
    user_data_dir = _get_dolphin_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_dolphin_profiles() -> List[Path]:
    """Get all Dolphin Anty profile directories."""
    profiles = []
    
    # Check main User Data dir
    user_data_dir = _get_dolphin_user_data_dir()
    if user_data_dir and user_data_dir.exists():
        try:
            for item in user_data_dir.iterdir():
                if item.is_dir():
                    if item.name == "Default" or item.name.startswith("Profile "):
                        profiles.append(item)
        except Exception:
            pass
    
    # Check browser profiles directory (profile-specific)
    browser_profiles_dir = _get_dolphin_browser_profiles_dir()
    if browser_profiles_dir and browser_profiles_dir.exists():
        try:
            for item in browser_profiles_dir.iterdir():
                if item.is_dir():
                    # Dolphin profiles are typically UUID-like directories
                    user_data = item / "User Data"
                    if user_data.exists():
                        default_profile = user_data / "Default"
                        if default_profile.exists():
                            profiles.append(default_profile)
        except Exception:
            pass
    
    return profiles


def load_dolphin_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """Load and decrypt Dolphin Anty's ABE key from Local State."""
    if local_state_path is None:
        local_state_path = _get_dolphin_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Dolphin Anty Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Dolphin Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # Dolphin uses Chrome mechanism
            return decrypt_abe_key(encrypted_key, BrowserType.CHROME, auto_detect=True)
        else:
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load Dolphin ABE key: {e}")
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


def decrypt_dolphin_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Dolphin cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise DolphinAppBoundDecryptionError("Decryption failed")
    return result


class DolphinAppBoundDecryptor(AppBoundDecryptor):
    """High-level interface for Dolphin App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        if local_state_path is None:
            local_state_path = _get_dolphin_local_state_path()
        # Dolphin uses Chrome's mechanism
        super().__init__(local_state_path, BrowserType.CHROME)
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_dolphin_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("Dolphin ABE decryptor initialized successfully")
        else:
            logger.warning("Dolphin ABE decryptor initialization failed")


def get_dolphin_cookies_via_cdp() -> List[Dict[str, Any]]:
    """Get decrypted Dolphin cookies using Chrome DevTools Protocol."""
    dolphin_path = _get_dolphin_exe_path()
    if not dolphin_path:
        logger.warning("Dolphin executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_dolphin_user_data_dir()
    
    try:
        with CDPCookieExtractor(dolphin_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"Dolphin CDP extraction failed: {e}")
        return []


def check_dolphin_abe_support() -> Dict[str, Any]:
    """Check system support for Dolphin Anty App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    result = check_abe_support()
    
    result["dolphin_installed"] = False
    result["dolphin_path"] = None
    result["dolphin_user_data_dir"] = None
    result["dolphin_browser_profiles_dir"] = None
    result["dolphin_profiles"] = []
    
    dolphin_path = _get_dolphin_exe_path()
    result["dolphin_installed"] = dolphin_path is not None
    if dolphin_path:
        result["dolphin_path"] = str(dolphin_path)
    
    user_data_dir = _get_dolphin_user_data_dir()
    if user_data_dir:
        result["dolphin_user_data_dir"] = str(user_data_dir)
    
    browser_profiles_dir = _get_dolphin_browser_profiles_dir()
    if browser_profiles_dir:
        result["dolphin_browser_profiles_dir"] = str(browser_profiles_dir)
    
    profiles = _get_dolphin_profiles()
    result["dolphin_profiles"] = [str(p) for p in profiles]
    
    return result


# Alias for DolphinAnty
check_dolphin_anty_abe_support = check_dolphin_abe_support


__all__ = [
    # Dolphin exports
    "DolphinAppBoundDecryptionError",
    "DolphinAppBoundDecryptor",
    "load_dolphin_abe_key_from_local_state",
    "decrypt_dolphin_v20_value",
    "get_dolphin_cookies_via_cdp",
    "check_dolphin_abe_support",
    # DolphinAnty aliases
    "DolphinAntyAppBoundDecryptionError",
    "check_dolphin_anty_abe_support",
    # Re-exports
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
