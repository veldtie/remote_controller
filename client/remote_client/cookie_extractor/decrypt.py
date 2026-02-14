from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING, Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CookieExportError

if TYPE_CHECKING:
    from .app_bound_encryption import AppBoundDecryptor
    from .app_bound_encryption_opera import OperaAppBoundDecryptor

logger = logging.getLogger(__name__)

_LOCAL_STATE_CACHE: dict[str, bytes | None] = {}
_ABE_DECRYPTOR_CACHE: dict[str, Optional[Union["AppBoundDecryptor", "OperaAppBoundDecryptor"]]] = {}


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


def _get_abe_decryptor(local_state_path: Path | None, browser_name: str = "chrome") -> Optional[Any]:
    """Get or create an ABE decryptor for the given Local State path."""
    if not local_state_path:
        return None
    
    cache_key = f"{browser_name}:{local_state_path}"
    if cache_key in _ABE_DECRYPTOR_CACHE:
        return _ABE_DECRYPTOR_CACHE[cache_key]
    
    # Browser-specific decryptors
    if browser_name == "opera":
        try:
            from .app_bound_encryption_opera import OperaAppBoundDecryptor
            decryptor = OperaAppBoundDecryptor(local_state_path)
            _ABE_DECRYPTOR_CACHE[cache_key] = decryptor
            return decryptor
        except ImportError:
            logger.debug("Opera ABE module not available")
            _ABE_DECRYPTOR_CACHE[cache_key] = None
            return None
    
    if browser_name == "edge":
        try:
            from .app_bound_encryption_edge import EdgeAppBoundDecryptor
            decryptor = EdgeAppBoundDecryptor(local_state_path)
            _ABE_DECRYPTOR_CACHE[cache_key] = decryptor
            return decryptor
        except ImportError:
            logger.debug("Edge ABE module not available")
            _ABE_DECRYPTOR_CACHE[cache_key] = None
            return None
    
    if browser_name == "brave":
        try:
            from .app_bound_encryption_brave import BraveAppBoundDecryptor
            decryptor = BraveAppBoundDecryptor(local_state_path)
            _ABE_DECRYPTOR_CACHE[cache_key] = decryptor
            return decryptor
        except ImportError:
            logger.debug("Brave ABE module not available")
            _ABE_DECRYPTOR_CACHE[cache_key] = None
            return None
    
    if browser_name == "dolphin_anty":
        try:
            from .app_bound_encryption_dolphin import DolphinAppBoundDecryptor
            decryptor = DolphinAppBoundDecryptor(local_state_path)
            _ABE_DECRYPTOR_CACHE[cache_key] = decryptor
            return decryptor
        except ImportError:
            logger.debug("Dolphin ABE module not available")
            _ABE_DECRYPTOR_CACHE[cache_key] = None
            return None
    
    # Default Chrome ABE decryptor for Chrome and other Chromium browsers
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


def _try_chrome_keyring_decrypt(encrypted_key: bytes, dpapi: Any) -> bytes | None:
    """
    Try to decrypt ABE key using Chrome's keyring file (app_bound_fixed_data).
    """
    try:
        chrome_user_data = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
        
        # Check for app_bound_fixed_data
        fixed_data_path = chrome_user_data / "Default" / "Network" / "app_bound_fixed_data"
        if not fixed_data_path.exists():
            fixed_data_path = chrome_user_data / "app_bound_fixed_data"
        
        if fixed_data_path.exists():
            logger.debug(f"Found app_bound_fixed_data at {fixed_data_path}")
            try:
                fixed_data = fixed_data_path.read_bytes()
                key_data = encrypted_key[4:] if encrypted_key.startswith(b"APPB") else encrypted_key
                
                decrypted = dpapi.CryptUnprotectData(key_data, None, fixed_data, None, 0)[1]
                if decrypted and len(decrypted) >= 16:
                    return decrypted
            except Exception as e:
                logger.debug(f"Chrome keyring decrypt with fixed_data failed: {e}")
        
        # Try from Local State
        local_state_path = chrome_user_data / "Local State"
        if local_state_path.exists():
            try:
                import json
                local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
                os_crypt = local_state.get("os_crypt", {})
                
                app_bound_key = os_crypt.get("app_bound_fixed_data")
                if app_bound_key:
                    additional_data = base64.b64decode(app_bound_key)
                    key_data = encrypted_key[4:] if encrypted_key.startswith(b"APPB") else encrypted_key
                    
                    decrypted = dpapi.CryptUnprotectData(key_data, None, additional_data, None, 0)[1]
                    if decrypted and len(decrypted) >= 16:
                        return decrypted
            except Exception as e:
                logger.debug(f"Chrome Local State keyring decrypt failed: {e}")
    except Exception as e:
        logger.debug(f"Chrome keyring method failed: {e}")
    
    return None


def _try_abe_key_decryption(encrypted_key: bytes, dpapi: Any, browser_name: str = "chrome") -> bytes | None:
    """
    Attempt to decrypt an App-Bound Encryption key.
    
    ABE keys start with 'APPB' prefix. Chrome 127+, Edge, Brave, Opera, Dolphin use this format.
    Uses multiple methods in order of reliability.
    """
    if not _is_abe_encrypted_key(encrypted_key):
        return None
    
    logger.info("Detected App-Bound Encryption key for %s", browser_name)
    
    key_data = encrypted_key[4:]  # Remove 'APPB' prefix
    
    # Method 1: Try IElevator COM interface first (most reliable for ABE)
    if browser_name == "opera":
        try:
            from .app_bound_encryption_opera import _try_opera_ielevator_com_decrypt
            result = _try_opera_ielevator_com_decrypt(encrypted_key)
            if result and len(result) >= 16:
                logger.info("Opera ABE key decrypted via IElevator COM")
                return result
        except ImportError:
            pass
    elif browser_name == "edge":
        try:
            from .app_bound_encryption_edge import _try_edge_ielevator_com_decrypt
            result = _try_edge_ielevator_com_decrypt(encrypted_key)
            if result and len(result) >= 16:
                logger.info("Edge ABE key decrypted via IElevator COM")
                return result
        except ImportError:
            pass
    elif browser_name == "brave":
        try:
            from .app_bound_encryption_brave import _try_brave_ielevator_com_decrypt
            result = _try_brave_ielevator_com_decrypt(encrypted_key)
            if result and len(result) >= 16:
                logger.info("Brave ABE key decrypted via IElevator COM")
                return result
        except ImportError:
            pass
    elif browser_name == "dolphin_anty":
        try:
            from .app_bound_encryption_dolphin import _try_dolphin_ielevator_com_decrypt
            result = _try_dolphin_ielevator_com_decrypt(encrypted_key)
            if result and len(result) >= 16:
                logger.info("Dolphin ABE key decrypted via IElevator COM")
                return result
        except ImportError:
            pass
    else:
        # Default Chrome IElevator
        try:
            from .app_bound_encryption import _try_ielevator_com_decrypt
            result = _try_ielevator_com_decrypt(encrypted_key)
            if result and len(result) >= 16:
                logger.info("ABE key decrypted via IElevator COM for %s", browser_name)
                return result
        except ImportError:
            pass
    
    # Method 2: Try Chrome keyring method (app_bound_fixed_data)
    result = _try_chrome_keyring_decrypt(encrypted_key, dpapi)
    if result and len(result) >= 16:
        logger.info("ABE key decrypted via Chrome keyring for %s", browser_name)
        return result
    
    # Method 3: Direct DPAPI (only works on some older configurations)
    try:
        decrypted = dpapi.CryptUnprotectData(key_data, None, None, None, 0)[1]
        if decrypted and len(decrypted) == 32:  # AES-256 key should be exactly 32 bytes
            logger.info("ABE key decrypted successfully via DPAPI for %s", browser_name)
            return decrypted
    except Exception as e:
        logger.debug("Direct DPAPI decryption of ABE key failed for %s: %s", browser_name, e)
    
    # Method 4: Try with CRYPTPROTECT_UI_FORBIDDEN flag
    try:
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        decrypted = dpapi.CryptUnprotectData(key_data, None, None, None, CRYPTPROTECT_UI_FORBIDDEN)[1]
        if decrypted and len(decrypted) == 32:
            logger.info("ABE key decrypted via DPAPI (UI_FORBIDDEN) for %s", browser_name)
            return decrypted
    except Exception:
        pass
    
    # Method 5: Try with LOCAL_MACHINE flag
    try:
        CRYPTPROTECT_LOCAL_MACHINE = 0x04
        decrypted = dpapi.CryptUnprotectData(key_data, None, None, None, CRYPTPROTECT_LOCAL_MACHINE)[1]
        if decrypted and len(decrypted) == 32:
            logger.info("ABE key decrypted via DPAPI (LOCAL_MACHINE) for %s", browser_name)
            return decrypted
    except Exception:
        pass
    
    # Method 6: Try decrypting full key with APPB prefix
    try:
        decrypted = dpapi.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        if decrypted and len(decrypted) == 32:
            logger.info("ABE key decrypted via full key DPAPI for %s", browser_name)
            return decrypted
    except Exception:
        pass
    
    logger.warning("ABE key decryption failed for %s - IElevator COM or alternative method required", browser_name)
    return None


def load_local_state_key(local_state_path: Path | None, dpapi: Any | None = None, browser_name: str = "chrome") -> bytes | None:
    """
    Load the encryption key from browser's Local State file.
    
    Supports both standard DPAPI keys and App-Bound Encryption (ABE) keys
    introduced in Chrome 127+ and adopted by Opera.
    """
    if not local_state_path or not local_state_path.exists():
        return None
    cache_key = f"{browser_name}:{local_state_path}"
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
    
    # Check for App-Bound Encryption (Chrome 127+, Opera)
    if _is_abe_encrypted_key(encrypted_key):
        key = _try_abe_key_decryption(encrypted_key, dpapi, browser_name)
        _LOCAL_STATE_CACHE[cache_key] = key
        return key
    
    # Standard DPAPI encryption (pre-Chrome 127)
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    
    try:
        key = dpapi.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except Exception as e:
        logger.debug("DPAPI decryption failed for %s: %s", browser_name, e)
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
