"""
App-Bound Encryption (ABE) module for Chrome 127+ cookie decryption.

Chrome 127+ uses App-Bound Encryption which ties encryption keys to the Chrome
application itself using Windows Data Protection API with application-specific
contexts. This module provides methods to decrypt such protected data.

Key concepts:
1. ABE wraps the DPAPI key with an additional layer tied to the Chrome executable
2. The encrypted_key in Local State starts with "APPB" prefix for ABE keys
3. Decryption requires either running as Chrome or using IElevator COM interface

References:
- https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- Chrome source: components/os_crypt/sync/os_crypt_win.cc
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CookieExportError

logger = logging.getLogger(__name__)

# ABE-specific constants
ABE_PREFIX = b"APPB"  # App-Bound prefix in encrypted key
V20_PREFIX = b"v20"  # Chrome 127+ uses v20 for ABE-encrypted values
DPAPI_PREFIX = b"DPAPI"

# AES-GCM parameters
AES_GCM_NONCE_LENGTH = 12
AES_GCM_TAG_LENGTH = 16


class AppBoundDecryptionError(CookieExportError):
    """Raised when App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("abe_decryption_failed", message)


def is_abe_encrypted_key(encrypted_key: bytes) -> bool:
    """Check if the key uses App-Bound Encryption (APPB prefix)."""
    return encrypted_key.startswith(ABE_PREFIX)


def is_abe_encrypted_value(encrypted_value: bytes) -> bool:
    """Check if a cookie value uses ABE encryption (v20 prefix)."""
    return encrypted_value.startswith(V20_PREFIX)


def _get_chrome_exe_path() -> Optional[Path]:
    """Find Chrome executable path."""
    possible_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return None


def _get_elevation_service_path() -> Optional[Path]:
    """Find Chrome Elevation Service executable."""
    chrome_path = _get_chrome_exe_path()
    if not chrome_path:
        return None
    elevation_service = chrome_path.parent / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    return None


def _try_ielevator_com_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """
    Attempt decryption using Chrome's IElevator COM interface.
    
    This is the official way to decrypt ABE data when not running as Chrome.
    Requires Chrome to be installed and the elevation service to be available.
    """
    if os.name != "nt":
        return None
    
    try:
        import comtypes.client  # type: ignore
        from comtypes import GUID  # type: ignore
        
        # Chrome's IElevator CLSID (Google Chrome Elevation Service)
        CLSID_Elevator = GUID("{708860E0-F641-4611-8895-7D867DD3675B}")
        IID_IElevator = GUID("{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}")
        
        try:
            elevator = comtypes.client.CreateObject(CLSID_Elevator, interface=IID_IElevator)
            decrypted = elevator.DecryptData(encrypted_data)
            return bytes(decrypted)
        except Exception as e:
            logger.debug("IElevator COM decryption failed: %s", e)
            return None
    except ImportError:
        logger.debug("comtypes not available for IElevator")
        return None


def _try_chrome_remote_debugging_decrypt(encrypted_key: bytes) -> Optional[bytes]:
    """
    Attempt to decrypt using Chrome's remote debugging interface.
    
    This method launches Chrome with remote debugging enabled and uses
    the DevTools protocol to access decryption functionality.
    """
    chrome_path = _get_chrome_exe_path()
    if not chrome_path:
        return None
    
    # This approach is complex and requires careful implementation
    # For now, we'll use other methods first
    return None


def _extract_abe_key_components(encrypted_key: bytes) -> Tuple[bytes, bytes]:
    """
    Extract components from an ABE-wrapped key.
    
    ABE key format after APPB prefix:
    - 4 bytes: version/header
    - Remaining: encrypted DPAPI blob with app binding
    """
    if not is_abe_encrypted_key(encrypted_key):
        raise AppBoundDecryptionError("Not an ABE-encrypted key")
    
    # Remove APPB prefix
    key_data = encrypted_key[len(ABE_PREFIX):]
    
    # The remaining data is a DPAPI blob with additional Chrome-specific binding
    return key_data[:4], key_data[4:]


def decrypt_abe_key_with_dpapi(encrypted_key: bytes) -> Optional[bytes]:
    """
    Attempt to decrypt an ABE key using DPAPI with Chrome's context.
    
    This method works when:
    1. Running with the same user context as Chrome
    2. On systems where ABE enforcement is relaxed
    """
    if os.name != "nt":
        return None
    
    try:
        import win32crypt  # type: ignore
        
        if is_abe_encrypted_key(encrypted_key):
            # Try direct DPAPI decryption after removing APPB prefix
            key_data = encrypted_key[len(ABE_PREFIX):]
            try:
                # Attempt decryption - may work if ABE binding is user-level only
                decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
                return decrypted
            except Exception as e:
                logger.debug("Direct DPAPI decryption of ABE key failed: %s", e)
        
        # Fallback: try decrypting with DPAPI prefix handling
        if encrypted_key.startswith(DPAPI_PREFIX):
            key_data = encrypted_key[len(DPAPI_PREFIX):]
            try:
                decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
                return decrypted
            except Exception:
                pass
    
    except ImportError:
        logger.debug("win32crypt not available")
    
    return None


def decrypt_abe_key_via_system_context(encrypted_key: bytes) -> Optional[bytes]:
    """
    Attempt ABE key decryption using SYSTEM context via scheduled task.
    
    This is an advanced technique that creates a temporary scheduled task
    running as SYSTEM to perform the decryption.
    """
    if os.name != "nt":
        return None
    
    # This requires admin privileges and is complex to implement safely
    # Reserved for future implementation
    return None


def load_abe_key_from_local_state(local_state_path: Path) -> Optional[bytes]:
    """
    Load and decrypt the ABE-protected key from Chrome's Local State.
    
    Args:
        local_state_path: Path to Chrome's Local State file
        
    Returns:
        Decrypted AES key or None if decryption fails
    """
    if not local_state_path.exists():
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except (KeyError, json.JSONDecodeError, Exception) as e:
        logger.debug("Failed to read encrypted key from Local State: %s", e)
        return None
    
    # Check if this is an ABE key
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Key is not ABE-encrypted, using standard DPAPI")
        return None  # Let the standard decrypt path handle it
    
    logger.info("Detected App-Bound Encryption key, attempting decryption...")
    
    # Try various decryption methods in order of preference
    
    # Method 1: IElevator COM interface (cleanest method)
    result = _try_ielevator_com_decrypt(encrypted_key)
    if result:
        logger.info("ABE key decrypted via IElevator COM")
        return result
    
    # Method 2: Direct DPAPI (works on some configurations)
    result = decrypt_abe_key_with_dpapi(encrypted_key)
    if result:
        logger.info("ABE key decrypted via DPAPI")
        return result
    
    # Method 3: SYSTEM context (requires elevation)
    result = decrypt_abe_key_via_system_context(encrypted_key)
    if result:
        logger.info("ABE key decrypted via SYSTEM context")
        return result
    
    logger.warning("All ABE decryption methods failed")
    return None


def decrypt_v20_value(
    encrypted_value: bytes,
    abe_key: bytes,
) -> str:
    """
    Decrypt a v20 (ABE) encrypted cookie value.
    
    v20 format:
    - 3 bytes: "v20" prefix
    - 12 bytes: AES-GCM nonce
    - Remaining: ciphertext + 16-byte auth tag
    
    Args:
        encrypted_value: The encrypted cookie value from database
        abe_key: The decrypted ABE key (32 bytes for AES-256)
        
    Returns:
        Decrypted plaintext value
    """
    if not is_abe_encrypted_value(encrypted_value):
        raise AppBoundDecryptionError("Value does not have v20 prefix")
    
    # Extract components
    nonce = encrypted_value[3:3 + AES_GCM_NONCE_LENGTH]
    ciphertext = encrypted_value[3 + AES_GCM_NONCE_LENGTH:]
    
    try:
        aesgcm = AESGCM(abe_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8", errors="replace")
    except Exception as e:
        raise AppBoundDecryptionError(f"AES-GCM decryption failed: {e}")


class AppBoundDecryptor:
    """
    High-level interface for App-Bound Encryption decryption.
    
    Usage:
        decryptor = AppBoundDecryptor(local_state_path)
        if decryptor.is_available():
            plaintext = decryptor.decrypt_value(encrypted_value)
    """
    
    def __init__(self, local_state_path: Optional[Path] = None):
        self._local_state_path = local_state_path
        self._abe_key: Optional[bytes] = None
        self._initialized = False
        self._available = False
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        
        if not self._local_state_path:
            return
        
        self._abe_key = load_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
    
    def is_available(self) -> bool:
        """Check if ABE decryption is available."""
        self._ensure_initialized()
        return self._available
    
    def can_decrypt_value(self, encrypted_value: bytes) -> bool:
        """Check if a value can be decrypted with ABE."""
        return is_abe_encrypted_value(encrypted_value) and self.is_available()
    
    def decrypt_value(self, encrypted_value: bytes) -> str:
        """
        Decrypt an ABE-encrypted cookie value.
        
        Args:
            encrypted_value: Encrypted value from cookies database
            
        Returns:
            Decrypted plaintext
            
        Raises:
            AppBoundDecryptionError: If decryption fails
        """
        self._ensure_initialized()
        
        if not self._available or not self._abe_key:
            raise AppBoundDecryptionError("ABE decryption not available")
        
        return decrypt_v20_value(encrypted_value, self._abe_key)


# Alternative approach using Chrome's Remote Debugging Protocol
def decrypt_via_chrome_devtools(
    local_state_path: Path,
    encrypted_values: list[bytes],
) -> list[Optional[str]]:
    """
    Decrypt values using Chrome's DevTools Protocol.
    
    This method:
    1. Launches Chrome with remote debugging
    2. Connects to DevTools
    3. Uses internal Chrome APIs to decrypt
    4. Returns decrypted values
    
    Note: This requires Chrome to be installed and may open a Chrome window.
    """
    chrome_path = _get_chrome_exe_path()
    if not chrome_path:
        return [None] * len(encrypted_values)
    
    # Implementation reserved for future versions
    # This approach requires careful handling of Chrome processes
    return [None] * len(encrypted_values)


def check_abe_support() -> dict[str, Any]:
    """
    Check system support for App-Bound Encryption decryption.
    
    Returns a dictionary with:
    - windows: Whether running on Windows
    - chrome_installed: Whether Chrome is found
    - elevation_service: Whether elevation service exists
    - ielevator_available: Whether IElevator COM is accessible
    - dpapi_available: Whether DPAPI is available
    """
    result = {
        "windows": os.name == "nt",
        "chrome_installed": False,
        "elevation_service": False,
        "ielevator_available": False,
        "dpapi_available": False,
    }
    
    if not result["windows"]:
        return result
    
    # Check Chrome installation
    chrome_path = _get_chrome_exe_path()
    result["chrome_installed"] = chrome_path is not None
    
    # Check elevation service
    if chrome_path:
        elevation_service = _get_elevation_service_path()
        result["elevation_service"] = elevation_service is not None
    
    # Check DPAPI availability
    try:
        import win32crypt  # type: ignore
        result["dpapi_available"] = True
    except ImportError:
        pass
    
    # Check IElevator COM
    try:
        import comtypes.client  # type: ignore
        result["ielevator_available"] = True
    except ImportError:
        pass
    
    return result
