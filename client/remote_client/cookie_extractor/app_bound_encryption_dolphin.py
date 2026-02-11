"""
App-Bound Encryption (ABE) module for Dolphin Anty browser cookie decryption.

Dolphin Anty is an anti-detect browser based on Chromium. It uses the same 
App-Bound Encryption mechanism as Chrome 127+. This module provides methods 
to decrypt Dolphin Anty's ABE-protected data.

Key differences from Chrome:
1. Dolphin Anty stores data in %LOCALAPPDATA%/Dolphin Anty/User Data/ or %APPDATA%/Dolphin Anty/
2. Dolphin Anty may have multiple browser profiles for anti-detection
3. Dolphin Anty uses Chrome's elevation service or its own

References:
- Chrome ABE: https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- Dolphin Anty is based on Chromium source code
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CookieExportError

logger = logging.getLogger(__name__)

# ABE-specific constants (same as Chrome)
ABE_PREFIX = b"APPB"
V20_PREFIX = b"v20"
DPAPI_PREFIX = b"DPAPI"

# AES-GCM parameters
AES_GCM_NONCE_LENGTH = 12
AES_GCM_TAG_LENGTH = 16


class DolphinAppBoundDecryptionError(CookieExportError):
    """Raised when Dolphin Anty App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("dolphin_abe_decryption_failed", message)


def is_abe_encrypted_key(encrypted_key: bytes) -> bool:
    """Check if the key uses App-Bound Encryption (APPB prefix)."""
    return encrypted_key.startswith(ABE_PREFIX)


def is_abe_encrypted_value(encrypted_value: bytes) -> bool:
    """Check if a cookie value uses ABE encryption (v20 prefix)."""
    return encrypted_value.startswith(V20_PREFIX)


def _get_dolphin_exe_path() -> Optional[Path]:
    """Find Dolphin Anty browser executable path."""
    possible_paths = [
        # Standard paths
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Dolphin Anty" / "Dolphin Anty.exe",
        # Alternative executable names
        Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "dolphin-anty.exe",
        Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "dolphin-anty.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try to find via registry
    if os.name == "nt":
        try:
            import winreg
            for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(hkey, r"SOFTWARE\Dolphin Anty") as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_path:
                            exe_names = ["Dolphin Anty.exe", "dolphin-anty.exe"]
                            for exe_name in exe_names:
                                dolphin_exe = Path(install_path) / exe_name
                                if dolphin_exe.exists():
                                    return dolphin_exe
                except FileNotFoundError:
                    continue
        except Exception:
            pass
    
    return None


def _get_dolphin_user_data_dir() -> Optional[Path]:
    """Get Dolphin Anty User Data directory."""
    if os.name == "nt":
        # Check multiple locations
        paths_to_check = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "User Data",
            Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "User Data",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty",
            Path(os.environ.get("APPDATA", "")) / "Dolphin Anty",
        ]
        for path in paths_to_check:
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
        # Try parent directory
        parent_local_state = user_data_dir.parent / "Local State"
        if parent_local_state.exists():
            return parent_local_state
    return None


def _get_dolphin_elevation_service_path() -> Optional[Path]:
    """Find Dolphin Anty Elevation Service executable."""
    dolphin_path = _get_dolphin_exe_path()
    if not dolphin_path:
        return None
    
    dolphin_dir = dolphin_path.parent
    
    try:
        for item in dolphin_dir.iterdir():
            if item.is_dir() and item.name[0].isdigit():
                elevation_service = item / "elevation_service.exe"
                if elevation_service.exists():
                    return elevation_service
    except Exception:
        pass
    
    elevation_service = dolphin_dir / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    
    return None


def _is_dolphin_elevation_service_running() -> bool:
    """Check if Dolphin Anty Elevation Service is running."""
    if os.name != "nt":
        return False
    # Dolphin Anty typically uses Chrome's elevation service
    try:
        result = subprocess.run(
            ["sc", "query", "GoogleChromeElevationService"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if "RUNNING" in result.stdout:
            return True
    except Exception:
        pass
    return False


def _try_dolphin_ielevator_com_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """Attempt decryption using IElevator COM interface."""
    if os.name != "nt":
        return None
    
    result = _try_dolphin_ielevator_comtypes(encrypted_data)
    if result:
        return result
    
    return None


def _try_dolphin_ielevator_comtypes(encrypted_data: bytes) -> Optional[bytes]:
    """Try Dolphin IElevator decryption using comtypes."""
    try:
        import comtypes.client
        from comtypes import GUID, COMMETHOD, HRESULT, IUnknown
        from ctypes import POINTER, c_char_p, c_ulong, byref
        
        class IElevator(IUnknown):
            _iid_ = GUID("{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}")
            _methods_ = [
                COMMETHOD([], HRESULT, 'RunRecoveryCRXElevated',
                          (['in'], c_char_p, 'crx_path'),
                          (['in'], c_char_p, 'browser_appid'),
                          (['in'], c_char_p, 'browser_version'),
                          (['in'], c_char_p, 'session_id'),
                          (['in'], c_ulong, 'caller_proc_id'),
                          (['out'], POINTER(c_ulong), 'proc_handle')),
                COMMETHOD([], HRESULT, 'EncryptData',
                          (['in'], c_ulong, 'protection_level'),
                          (['in'], c_char_p, 'plaintext'),
                          (['in'], c_ulong, 'plaintext_len'),
                          (['out'], POINTER(c_char_p), 'ciphertext'),
                          (['out'], POINTER(c_ulong), 'ciphertext_len')),
                COMMETHOD([], HRESULT, 'DecryptData',
                          (['in'], c_char_p, 'ciphertext'),
                          (['in'], c_ulong, 'ciphertext_len'),
                          (['out'], POINTER(c_char_p), 'plaintext'),
                          (['out'], POINTER(c_ulong), 'plaintext_len')),
            ]
        
        # Dolphin typically uses Chrome's CLSIDs
        clsids = [
            "{708860E0-F641-4611-8895-7D867DD3675B}",  # Chrome Stable
            "{DD2646BA-3707-4BF8-B9A7-038691A68FC2}",  # Chrome Beta
        ]
        
        comtypes.client.CoInitialize()
        
        for clsid_str in clsids:
            try:
                clsid = GUID(clsid_str)
                obj = comtypes.client.CreateObject(clsid, interface=IElevator)
                
                if obj:
                    plaintext = c_char_p()
                    plaintext_len = c_ulong()
                    
                    hr = obj.DecryptData(
                        encrypted_data,
                        len(encrypted_data),
                        byref(plaintext),
                        byref(plaintext_len)
                    )
                    
                    if hr == 0 and plaintext.value:
                        result = plaintext.value[:plaintext_len.value]
                        logger.info(f"Dolphin ABE decrypted via IElevator COM with CLSID {clsid_str}")
                        return result
            except Exception as e:
                logger.debug(f"Dolphin IElevator attempt failed for {clsid_str}: {e}")
                continue
        
        comtypes.client.CoUninitialize()
        
    except ImportError:
        logger.debug("comtypes not available for Dolphin IElevator")
    except Exception as e:
        logger.debug(f"Dolphin IElevator comtypes failed: {e}")
    
    return None


def decrypt_dolphin_abe_key_with_dpapi(encrypted_key: bytes) -> Optional[bytes]:
    """Try to decrypt Dolphin Anty ABE key using Windows DPAPI."""
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        return None
    
    try:
        import win32crypt
    except ImportError:
        logger.debug("win32crypt not available")
        return None
    
    key_data = encrypted_key[4:]
    
    try:
        decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
        logger.debug("Dolphin ABE key decrypted via DPAPI")
        return decrypted
    except Exception as e:
        logger.debug(f"Dolphin DPAPI decryption failed: {e}")
    
    return None


def decrypt_dolphin_abe_key_via_system_context(encrypted_key: bytes) -> Optional[bytes]:
    """Attempt decryption using SYSTEM context."""
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        return None
    
    try:
        import win32crypt
        key_data = encrypted_key[4:]
        decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
        return decrypted
    except Exception as e:
        logger.debug(f"Dolphin SYSTEM context decryption failed: {e}")
    
    return None


def load_dolphin_abe_key_from_local_state(local_state_path: Optional[Path] = None) -> Optional[bytes]:
    """Load and decrypt the ABE key from Dolphin Anty's Local State file."""
    if local_state_path is None:
        local_state_path = _get_dolphin_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except (KeyError, json.JSONDecodeError, Exception) as e:
        logger.debug("Failed to read encrypted key from Dolphin Local State: %s", e)
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Dolphin key is not ABE-encrypted, using standard DPAPI")
        return None
    
    logger.info("Detected Dolphin Anty App-Bound Encryption key, attempting decryption...")
    
    result = _try_dolphin_ielevator_com_decrypt(encrypted_key)
    if result:
        logger.info("Dolphin ABE key decrypted via IElevator COM")
        return result
    
    result = decrypt_dolphin_abe_key_with_dpapi(encrypted_key)
    if result:
        logger.info("Dolphin ABE key decrypted via DPAPI")
        return result
    
    result = decrypt_dolphin_abe_key_via_system_context(encrypted_key)
    if result:
        logger.info("Dolphin ABE key decrypted via SYSTEM context")
        return result
    
    logger.warning("All Dolphin ABE decryption methods failed")
    return None


def decrypt_dolphin_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Dolphin Anty cookie value."""
    if not is_abe_encrypted_value(encrypted_value):
        raise DolphinAppBoundDecryptionError("Value does not have v20 prefix")
    
    nonce = encrypted_value[3:3 + AES_GCM_NONCE_LENGTH]
    ciphertext = encrypted_value[3 + AES_GCM_NONCE_LENGTH:]
    
    try:
        aesgcm = AESGCM(abe_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8", errors="replace")
    except Exception as e:
        raise DolphinAppBoundDecryptionError(f"AES-GCM decryption failed: {e}")


class DolphinAppBoundDecryptor:
    """High-level interface for Dolphin Anty App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        self._local_state_path = local_state_path or _get_dolphin_local_state_path()
        self._abe_key: Optional[bytes] = None
        self._initialized = False
        self._available = False
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        if not self._local_state_path:
            return
        self._abe_key = load_dolphin_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
    
    def is_available(self) -> bool:
        self._ensure_initialized()
        return self._available
    
    def can_decrypt_value(self, encrypted_value: bytes) -> bool:
        return is_abe_encrypted_value(encrypted_value) and self.is_available()
    
    def decrypt_value(self, encrypted_value: bytes) -> str:
        self._ensure_initialized()
        if not self._available or not self._abe_key:
            raise DolphinAppBoundDecryptionError("Dolphin ABE decryption not available")
        return decrypt_dolphin_v20_value(encrypted_value, self._abe_key)


def check_dolphin_abe_support() -> dict[str, Any]:
    """Check system support for Dolphin Anty App-Bound Encryption decryption."""
    result = {
        "windows": os.name == "nt",
        "dolphin_installed": False,
        "dolphin_path": None,
        "user_data_dir": None,
        "elevation_service": False,
        "elevation_service_path": None,
        "elevation_service_running": False,
        "ielevator_available": False,
        "dpapi_available": False,
        "cdp_available": False,
        "dolphin_version": None,
        "recommended_method": None,
    }
    
    if not result["windows"]:
        result["recommended_method"] = "unsupported_platform"
        return result
    
    dolphin_path = _get_dolphin_exe_path()
    result["dolphin_installed"] = dolphin_path is not None
    if dolphin_path:
        result["dolphin_path"] = str(dolphin_path)
    
    user_data_dir = _get_dolphin_user_data_dir()
    if user_data_dir:
        result["user_data_dir"] = str(user_data_dir)
    
    if dolphin_path:
        elevation_service = _get_dolphin_elevation_service_path()
        result["elevation_service"] = elevation_service is not None
        if elevation_service:
            result["elevation_service_path"] = str(elevation_service)
    
    result["elevation_service_running"] = _is_dolphin_elevation_service_running()
    
    try:
        import win32crypt
        result["dpapi_available"] = True
    except ImportError:
        pass
    
    try:
        import comtypes.client
        from comtypes import GUID
        CLSID_Elevator = GUID("{708860E0-F641-4611-8895-7D867DD3675B}")
        try:
            comtypes.client.CoInitialize()
            obj = comtypes.client.CreateObject(CLSID_Elevator)
            result["ielevator_available"] = obj is not None
        except Exception:
            result["ielevator_available"] = False
        finally:
            try:
                comtypes.client.CoUninitialize()
            except:
                pass
    except ImportError:
        pass
    
    # Check CDP availability (preferred method for ABE)
    if result["dolphin_installed"]:
        try:
            try:
                import websocket
                result["cdp_available"] = True
            except ImportError:
                try:
                    import websockets
                    result["cdp_available"] = True
                except ImportError:
                    result["cdp_available"] = False
        except Exception:
            result["cdp_available"] = False
    
    result["dolphin_version"] = _get_dolphin_version()
    
    # Determine recommended method
    if result["cdp_available"]:
        result["recommended_method"] = "cdp"
    elif result["ielevator_available"]:
        result["recommended_method"] = "ielevator"
    elif result["dpapi_available"]:
        result["recommended_method"] = "dpapi"
    else:
        result["recommended_method"] = "none"
    
    return result


def get_dolphin_cookies_via_cdp() -> list[dict]:
    """
    Get decrypted Dolphin Anty cookies using Chrome DevTools Protocol.
    
    This is the recommended method for Dolphin with ABE.
    """
    try:
        from .app_bound_encryption import CDPCookieExtractor
        
        dolphin_path = _get_dolphin_exe_path()
        if not dolphin_path:
            logger.warning("Dolphin Anty executable not found for CDP extraction")
            return []
        
        user_data_dir = _get_dolphin_user_data_dir()
        
        with CDPCookieExtractor(dolphin_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
            
    except Exception as e:
        logger.error(f"Dolphin CDP extraction failed: {e}")
        return []


def _get_dolphin_version() -> Optional[str]:
    """Get Dolphin Anty version."""
    if os.name != "nt":
        return None
    
    local_state = _get_dolphin_local_state_path()
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
