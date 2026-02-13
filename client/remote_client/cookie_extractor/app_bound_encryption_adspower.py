"""
App-Bound Encryption (ABE) module for AdsPower browser cookie decryption.

AdsPower is a Chromium-based antidetect browser that uses the same
App-Bound Encryption mechanism as Chrome 127+. This module provides
AdsPower-specific methods using the unified ABE native module.

Key differences:
1. AdsPower stores data in %LOCALAPPDATA%/AdsPower/ or %APPDATA%/AdsPower/
2. AdsPower uses Chrome's elevation service mechanism
3. AdsPower has multiple browser profile directories for different profiles
4. AdsPower profiles may be stored in separate directories with unique IDs

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


class AdsPowerAppBoundDecryptionError(CookieExportError):
    """Raised when AdsPower App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("adspower_abe_decryption_failed", message)


def _get_adspower_exe_path() -> Optional[Path]:
    """Find AdsPower executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower" / "AdsPower.exe",
        Path(os.environ.get("APPDATA", "")) / "AdsPower" / "AdsPower.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower Global" / "AdsPower.exe",
        Path(os.environ.get("APPDATA", "")) / "AdsPower Global" / "AdsPower.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "AdsPower" / "AdsPower.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "AdsPower" / "AdsPower.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
    try:
        import winreg
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\AdsPower") as key:
                    install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if install_path:
                        exe = Path(install_path) / "AdsPower.exe"
                        if exe.exists():
                            return exe
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    return None


def _get_adspower_user_data_dir() -> Optional[Path]:
    """Get AdsPower User Data directory."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "AdsPower" / "User Data",
        Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower Global" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "AdsPower Global" / "User Data",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_adspower_browser_data_dir() -> Optional[Path]:
    """Get AdsPower browser cache/data directory (for individual profiles)."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower" / "browser_cache",
        Path(os.environ.get("APPDATA", "")) / "AdsPower" / "browser_cache",
        Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower Global" / "browser_cache",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_adspower_local_state_path() -> Optional[Path]:
    """Get AdsPower Local State file path."""
    user_data_dir = _get_adspower_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_adspower_profiles() -> List[Path]:
    """Get all AdsPower profile directories."""
    profiles = []
    
    # Check main User Data dir
    user_data_dir = _get_adspower_user_data_dir()
    if user_data_dir and user_data_dir.exists():
        try:
            for item in user_data_dir.iterdir():
                if item.is_dir():
                    if item.name == "Default" or item.name.startswith("Profile "):
                        profiles.append(item)
        except Exception:
            pass
    
    # Check browser cache directory (profile-specific)
    browser_data_dir = _get_adspower_browser_data_dir()
    if browser_data_dir and browser_data_dir.exists():
        try:
            for item in browser_data_dir.iterdir():
                if item.is_dir():
                    # AdsPower profiles are typically UUID-like directories
                    user_data = item / "User Data"
                    if user_data.exists():
                        profiles.append(user_data / "Default")
        except Exception:
            pass
    
    return profiles


def load_adspower_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """Load and decrypt AdsPower's ABE key from Local State."""
    if local_state_path is None:
        local_state_path = _get_adspower_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("AdsPower Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in AdsPower Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # AdsPower uses Chrome mechanism
            return decrypt_abe_key(encrypted_key, BrowserType.CHROME, auto_detect=True)
        else:
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load AdsPower ABE key: {e}")
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


def decrypt_adspower_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted AdsPower cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise AdsPowerAppBoundDecryptionError("Decryption failed")
    return result


class AdsPowerAppBoundDecryptor(AppBoundDecryptor):
    """High-level interface for AdsPower App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        if local_state_path is None:
            local_state_path = _get_adspower_local_state_path()
        # AdsPower uses Chrome's mechanism
        super().__init__(local_state_path, BrowserType.CHROME)
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_adspower_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("AdsPower ABE decryptor initialized successfully")
        else:
            logger.warning("AdsPower ABE decryptor initialization failed")


def get_adspower_cookies_via_cdp() -> List[Dict[str, Any]]:
    """Get decrypted AdsPower cookies using Chrome DevTools Protocol."""
    adspower_path = _get_adspower_exe_path()
    if not adspower_path:
        logger.warning("AdsPower executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_adspower_user_data_dir()
    
    try:
        with CDPCookieExtractor(adspower_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"AdsPower CDP extraction failed: {e}")
        return []


def check_adspower_abe_support() -> Dict[str, Any]:
    """Check system support for AdsPower App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    result = check_abe_support()
    
    result["adspower_installed"] = False
    result["adspower_path"] = None
    result["adspower_user_data_dir"] = None
    result["adspower_browser_cache_dir"] = None
    result["adspower_profiles"] = []
    
    adspower_path = _get_adspower_exe_path()
    result["adspower_installed"] = adspower_path is not None
    if adspower_path:
        result["adspower_path"] = str(adspower_path)
    
    user_data_dir = _get_adspower_user_data_dir()
    if user_data_dir:
        result["adspower_user_data_dir"] = str(user_data_dir)
    
    browser_data_dir = _get_adspower_browser_data_dir()
    if browser_data_dir:
        result["adspower_browser_cache_dir"] = str(browser_data_dir)
    
    profiles = _get_adspower_profiles()
    result["adspower_profiles"] = [str(p) for p in profiles]
    
    return result


__all__ = [
    "AdsPowerAppBoundDecryptionError",
    "AdsPowerAppBoundDecryptor",
    "load_adspower_abe_key_from_local_state",
    "decrypt_adspower_v20_value",
    "get_adspower_cookies_via_cdp",
    "check_adspower_abe_support",
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
