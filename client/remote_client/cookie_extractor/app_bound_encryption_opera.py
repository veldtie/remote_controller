"""
App-Bound Encryption (ABE) module for Opera browser cookie decryption.

Opera is based on Chromium and uses the same App-Bound Encryption mechanism
as Chrome 127+. This module provides Opera-specific methods using the unified
ABE native module.

Key differences from Chrome:
1. Opera stores data in %APPDATA%/Opera Software/Opera Stable/
2. Opera uses Chrome's elevation service mechanism but with Opera-specific paths

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


class OperaAppBoundDecryptionError(CookieExportError):
    """Raised when Opera App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("opera_abe_decryption_failed", message)


def _get_opera_exe_path() -> Optional[Path]:
    """Find Opera browser executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Opera" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera" / "opera.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera" / "opera.exe",
        Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable" / "opera.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
    try:
        import winreg
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\Opera Software") as key:
                    install_path, _ = winreg.QueryValueEx(key, "Last Install Path")
                    if install_path:
                        opera_exe = Path(install_path) / "opera.exe"
                        if opera_exe.exists():
                            return opera_exe
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    return None


def _get_opera_user_data_dir() -> Optional[Path]:
    """Get Opera User Data directory."""
    if os.name != "nt":
        return None
    app_data = os.environ.get("APPDATA", "")
    if app_data:
        path = Path(app_data) / "Opera Software" / "Opera Stable"
        if path.exists():
            return path
    return None


def _get_opera_local_state_path() -> Optional[Path]:
    """Get Opera Local State file path."""
    user_data_dir = _get_opera_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def load_opera_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """Load and decrypt Opera's ABE key from Local State."""
    if local_state_path is None:
        local_state_path = _get_opera_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Opera Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Opera Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # Opera uses Chrome mechanism, try Chrome first then auto-detect
            return decrypt_abe_key(encrypted_key, BrowserType.CHROME, auto_detect=True)
        else:
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load Opera ABE key: {e}")
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


def decrypt_opera_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Opera cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise OperaAppBoundDecryptionError("Decryption failed")
    return result


class OperaAppBoundDecryptor(AppBoundDecryptor):
    """High-level interface for Opera App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        if local_state_path is None:
            local_state_path = _get_opera_local_state_path()
        super().__init__(local_state_path, BrowserType.OPERA)
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_opera_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("Opera ABE decryptor initialized successfully")
        else:
            logger.warning("Opera ABE decryptor initialization failed")


def get_opera_cookies_via_cdp() -> List[Dict[str, Any]]:
    """Get decrypted Opera cookies using Chrome DevTools Protocol."""
    opera_path = _get_opera_exe_path()
    if not opera_path:
        logger.warning("Opera executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_opera_user_data_dir()
    
    try:
        with CDPCookieExtractor(opera_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"Opera CDP extraction failed: {e}")
        return []


def check_opera_abe_support() -> Dict[str, Any]:
    """Check system support for Opera App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    result = check_abe_support()
    
    result["opera_installed"] = False
    result["opera_path"] = None
    result["opera_user_data_dir"] = None
    
    opera_path = _get_opera_exe_path()
    result["opera_installed"] = opera_path is not None
    if opera_path:
        result["opera_path"] = str(opera_path)
    
    user_data_dir = _get_opera_user_data_dir()
    if user_data_dir:
        result["opera_user_data_dir"] = str(user_data_dir)
    
    return result


__all__ = [
    "OperaAppBoundDecryptionError",
    "OperaAppBoundDecryptor",
    "load_opera_abe_key_from_local_state",
    "decrypt_opera_v20_value",
    "get_opera_cookies_via_cdp",
    "check_opera_abe_support",
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
