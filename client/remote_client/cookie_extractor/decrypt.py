from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CookieExportError

if TYPE_CHECKING:
    from .app_bound_encryption import AppBoundDecryptor

logger = logging.getLogger(__name__)

_LOCAL_STATE_CACHE: dict[str, bytes | None] = {}
_ABE_DECRYPTOR_CACHE: dict[str, Optional["AppBoundDecryptor"]] = {}


def get_dpapi() -> Any:
    if os.name != "nt":
        raise CookieExportError("unsupported", "Cookie export is only supported on Windows.")
    try:
        import win32crypt  # type: ignore
    except Exception as exc:
        raise CookieExportError(
            "missing_dependency", "win32crypt is not available."
        ) from exc
    return win32crypt


def _get_abe_decryptor(local_state_path: Path | None) -> Optional["AppBoundDecryptor"]:
    """Get or create an ABE decryptor for the given Local State path."""
    if not local_state_path:
        return None
    
    cache_key = str(local_state_path)
    if cache_key in _ABE_DECRYPTOR_CACHE:
        return _ABE_DECRYPTOR_CACHE[cache_key]
    
    try:
        from .app_bound_encryption import AppBoundDecryptor
        decryptor = AppBoundDecryptor(local_state_path)
        _ABE_DECRYPTOR_CACHE[cache_key] = decryptor
        return decryptor
    except ImportError:
        logger.debug("ABE module not available")
        _ABE_DECRYPTOR_CACHE[cache_key] = None
        return None


def _is_abe_encrypted_key(encrypted_key: bytes) -> bool:
    """Check if the key uses App-Bound Encryption (APPB prefix)."""
    return encrypted_key.startswith(b"APPB")


def _try_abe_key_decryption(encrypted_key: bytes, dpapi: Any) -> bytes | None:
    """
    Attempt to decrypt an App-Bound Encryption key.
    
    ABE keys start with 'APPB' prefix. Chrome 127+ uses this format.
    """
    if not _is_abe_encrypted_key(encrypted_key):
        return None
    
    logger.info("Detected App-Bound Encryption (Chrome 127+) key")
    
    # Remove APPB prefix and try DPAPI decryption
    # This may work on some configurations where ABE enforcement is relaxed
    key_data = encrypted_key[4:]  # Remove 'APPB' prefix
    
    try:
        key = dpapi.CryptUnprotectData(key_data, None, None, None, 0)[1]
        logger.info("ABE key decrypted successfully via DPAPI")
        return key
    except Exception as e:
        logger.debug("Direct DPAPI decryption of ABE key failed: %s", e)
    
    # Try using IElevator COM interface if available
    try:
        from .app_bound_encryption import _try_ielevator_com_decrypt
        result = _try_ielevator_com_decrypt(encrypted_key)
        if result:
            logger.info("ABE key decrypted via IElevator COM")
            return result
    except ImportError:
        pass
    
    logger.warning("ABE key decryption failed - Chrome may need to be running or use alternative methods")
    return None


def load_local_state_key(local_state_path: Path | None, dpapi: Any | None = None) -> bytes | None:
    """
    Load the encryption key from Chrome's Local State file.
    
    Supports both standard DPAPI keys and App-Bound Encryption (ABE) keys
    introduced in Chrome 127+.
    """
    if not local_state_path or not local_state_path.exists():
        return None
    cache_key = str(local_state_path)
    if cache_key in _LOCAL_STATE_CACHE:
        return _LOCAL_STATE_CACHE[cache_key]
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
    except Exception:
        _LOCAL_STATE_CACHE[cache_key] = None
        return None
    try:
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except Exception:
        _LOCAL_STATE_CACHE[cache_key] = None
        return None
    
    if dpapi is None:
        dpapi = get_dpapi()
    
    # Check for App-Bound Encryption (Chrome 127+)
    if _is_abe_encrypted_key(encrypted_key):
        key = _try_abe_key_decryption(encrypted_key, dpapi)
        _LOCAL_STATE_CACHE[cache_key] = key
        return key
    
    # Standard DPAPI encryption (pre-Chrome 127)
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    
    try:
        key = dpapi.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except Exception as e:
        logger.debug("DPAPI decryption failed: %s", e)
        key = None
    _LOCAL_STATE_CACHE[cache_key] = key
    return key


def decrypt_chrome_value(
    encrypted_value: bytes | memoryview,
    dpapi: Any,
    local_state_key: bytes | None,
    abe_decryptor: Optional["AppBoundDecryptor"] = None,
) -> str:
    """
    Decrypt a Chrome encrypted cookie value.
    
    Supports:
    - v10/v11/v12: Standard AES-GCM encryption with DPAPI-protected key
    - v20: App-Bound Encryption (Chrome 127+)
    - Legacy: Direct DPAPI encryption
    
    Args:
        encrypted_value: The encrypted cookie value
        dpapi: win32crypt module for DPAPI operations
        local_state_key: Decrypted key from Local State (for v10/v11/v12)
        abe_decryptor: Optional ABE decryptor for v20 values
        
    Returns:
        Decrypted cookie value as string
    """
    if isinstance(encrypted_value, memoryview):
        encrypted_bytes = encrypted_value.tobytes()
    else:
        encrypted_bytes = bytes(encrypted_value)
    if not encrypted_bytes:
        return ""
    
    # v20: App-Bound Encryption (Chrome 127+)
    if encrypted_bytes.startswith(b"v20"):
        if abe_decryptor and abe_decryptor.is_available():
            try:
                return abe_decryptor.decrypt_value(encrypted_bytes)
            except Exception as e:
                logger.debug("ABE decryption failed for v20 value: %s", e)
        
        # Fallback: Try using the local_state_key if available
        # Some ABE configurations may still use the same key format
        if local_state_key:
            nonce = encrypted_bytes[3:15]
            ciphertext = encrypted_bytes[15:]
            try:
                decrypted = AESGCM(local_state_key).decrypt(nonce, ciphertext, None)
                return decrypted.decode("utf-8", errors="replace")
            except Exception as e:
                logger.debug("v20 AES-GCM decryption with local_state_key failed: %s", e)
        
        return "[abe_decrypt_failed]"
    
    # v10/v11/v12: Standard AES-GCM encryption
    if encrypted_bytes.startswith((b"v10", b"v11", b"v12")):
        if local_state_key:
            nonce = encrypted_bytes[3:15]
            ciphertext = encrypted_bytes[15:]
            try:
                decrypted = AESGCM(local_state_key).decrypt(nonce, ciphertext, None)
                return decrypted.decode("utf-8", errors="replace")
            except Exception as e:
                logger.debug("AES-GCM decryption failed: %s", e)
    
    # Legacy: Direct DPAPI encryption
    try:
        decrypted = dpapi.CryptUnprotectData(encrypted_bytes, None, None, None, 0)[1]
        return decrypted.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("DPAPI decryption failed: %s", e)
        return "[decrypt_failed]"


def clear_key_cache() -> None:
    """Clear all cached keys and decryptors."""
    _LOCAL_STATE_CACHE.clear()
    _ABE_DECRYPTOR_CACHE.clear()
