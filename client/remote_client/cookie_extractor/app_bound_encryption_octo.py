"""
App-Bound Encryption (ABE) module for Octo Browser cookie decryption.

Octo Browser is a Chromium-based antidetect browser that uses the same
App-Bound Encryption mechanism as Chrome 127+. This module provides
Octo-specific methods using the unified ABE native module.

Key differences:
1. Octo stores data in %LOCALAPPDATA%/Octo Browser/User Data/ or %APPDATA%/Octo Browser/
2. Octo uses Chrome's elevation service mechanism
3. Octo may have multiple profile directories for different browser profiles

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


class OctoAppBoundDecryptionError(CookieExportError):
    """Raised when Octo Browser App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("octo_abe_decryption_failed", message)


def _get_octo_exe_path() -> Optional[Path]:
    """Find Octo Browser executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Octo Browser" / "OctoBrowser.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Octo Browser" / "Application" / "OctoBrowser.exe",
        Path(os.environ.get("APPDATA", "")) / "Octo Browser" / "OctoBrowser.exe",
        Path(os.environ.get("APPDATA", "")) / "Octo Browser" / "Application" / "OctoBrowser.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Octo Browser" / "OctoBrowser.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Octo Browser" / "OctoBrowser.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
    try:
        import winreg
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\Octo Browser") as key:
                    install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if install_path:
                        exe = Path(install_path) / "OctoBrowser.exe"
                        if exe.exists():
                            return exe
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    return None


def _get_octo_user_data_dir() -> Optional[Path]:
    """Get Octo Browser User Data directory."""
    if os.name != "nt":
        return None
    
    possible_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Octo Browser" / "User Data",
        Path(os.environ.get("APPDATA", "")) / "Octo Browser" / "User Data",
    ]
    
    for path in possible_dirs:
        if path.exists():
            return path
    
    return None


def _get_octo_local_state_path() -> Optional[Path]:
    """Get Octo Browser Local State file path."""
    user_data_dir = _get_octo_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_octo_profiles() -> List[Path]:
    """Get all Octo Browser profile directories."""
    profiles = []
    user_data_dir = _get_octo_user_data_dir()
    if not user_data_dir or not user_data_dir.exists():
        return profiles
    
    try:
        for item in user_data_dir.iterdir():
            if item.is_dir():
                # Check for Default profile or Profile N directories
                if item.name == "Default" or item.name.startswith("Profile "):
                    profiles.append(item)
    except Exception:
        pass
    
    return profiles


def load_octo_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """Load and decrypt Octo Browser's ABE key from Local State."""
    if local_state_path is None:
        local_state_path = _get_octo_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Octo Browser Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Octo Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # Octo uses Chrome mechanism
            return decrypt_abe_key(encrypted_key, BrowserType.CHROME, auto_detect=True)
        else:
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load Octo ABE key: {e}")
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


def decrypt_octo_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Octo cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise OctoAppBoundDecryptionError("Decryption failed")
    return result


class OctoAppBoundDecryptor(AppBoundDecryptor):
    """High-level interface for Octo Browser App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        if local_state_path is None:
            local_state_path = _get_octo_local_state_path()
        # Octo uses Chrome's mechanism
        super().__init__(local_state_path, BrowserType.CHROME)
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_octo_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("Octo Browser ABE decryptor initialized successfully")
        else:
            logger.warning("Octo Browser ABE decryptor initialization failed")


def get_octo_cookies_via_cdp() -> List[Dict[str, Any]]:
    """Get decrypted Octo Browser cookies using Chrome DevTools Protocol."""
    octo_path = _get_octo_exe_path()
    if not octo_path:
        logger.warning("Octo Browser executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_octo_user_data_dir()
    
    try:
        with CDPCookieExtractor(octo_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"Octo Browser CDP extraction failed: {e}")
        return []


def check_octo_abe_support() -> Dict[str, Any]:
    """Check system support for Octo Browser App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    result = check_abe_support()
    
    result["octo_installed"] = False
    result["octo_path"] = None
    result["octo_user_data_dir"] = None
    result["octo_profiles"] = []
    
    octo_path = _get_octo_exe_path()
    result["octo_installed"] = octo_path is not None
    if octo_path:
        result["octo_path"] = str(octo_path)
    
    user_data_dir = _get_octo_user_data_dir()
    if user_data_dir:
        result["octo_user_data_dir"] = str(user_data_dir)
    
    profiles = _get_octo_profiles()
    result["octo_profiles"] = [str(p) for p in profiles]
    
    return result


__all__ = [
    "OctoAppBoundDecryptionError",
    "OctoAppBoundDecryptor",
    "load_octo_abe_key_from_local_state",
    "decrypt_octo_v20_value",
    "get_octo_cookies_via_cdp",
    "check_octo_abe_support",
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
