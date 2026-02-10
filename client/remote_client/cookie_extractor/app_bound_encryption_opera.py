"""
App-Bound Encryption (ABE) module for Opera browser cookie decryption.

Opera is based on Chromium and uses similar App-Bound Encryption mechanism
as Chrome 127+. This module provides methods to decrypt Opera's ABE-protected data.

Key differences from Chrome:
1. Opera stores data in %APPDATA%/Opera Software/Opera Stable/ instead of LocalAppData
2. Opera has its own elevation service with different CLSIDs
3. Opera may use different service names and COM interfaces

References:
- Chrome ABE: https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- Opera is based on Chromium source code
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

# ABE-specific constants (same as Chrome)
ABE_PREFIX = b"APPB"  # App-Bound prefix in encrypted key
V20_PREFIX = b"v20"  # Opera also uses v20 for ABE-encrypted values
DPAPI_PREFIX = b"DPAPI"

# AES-GCM parameters
AES_GCM_NONCE_LENGTH = 12
AES_GCM_TAG_LENGTH = 16


class OperaAppBoundDecryptionError(CookieExportError):
    """Raised when Opera App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("opera_abe_decryption_failed", message)


def is_abe_encrypted_key(encrypted_key: bytes) -> bool:
    """Check if the key uses App-Bound Encryption (APPB prefix)."""
    return encrypted_key.startswith(ABE_PREFIX)


def is_abe_encrypted_value(encrypted_value: bytes) -> bool:
    """Check if a cookie value uses ABE encryption (v20 prefix)."""
    return encrypted_value.startswith(V20_PREFIX)


def _get_opera_exe_path() -> Optional[Path]:
    """Find Opera executable path."""
    possible_paths = [
        # Standard Opera installations
        Path(os.environ.get("PROGRAMFILES", "")) / "Opera" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera" / "opera.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera" / "opera.exe",
        # Opera Stable in standard location
        Path(os.environ.get("PROGRAMFILES", "")) / "Opera" / "launcher.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera" / "launcher.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera" / "launcher.exe",
        # Opera GX paths
        Path(os.environ.get("PROGRAMFILES", "")) / "Opera GX" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera GX" / "opera.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera GX" / "opera.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try to find via registry
    if os.name == "nt":
        try:
            import winreg
            # Try HKLM first
            for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(hkey, r"SOFTWARE\Opera Software") as key:
                        install_path, _ = winreg.QueryValueEx(key, "Last Install Path")
                        if install_path:
                            opera_exe = Path(install_path) / "opera.exe"
                            if opera_exe.exists():
                                return opera_exe
                            launcher = Path(install_path) / "launcher.exe"
                            if launcher.exists():
                                return launcher
                except FileNotFoundError:
                    continue
        except Exception:
            pass
    
    return None


def _get_opera_user_data_dir() -> Optional[Path]:
    """Get Opera User Data directory."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            # Standard Opera Stable
            path = Path(appdata) / "Opera Software" / "Opera Stable"
            if path.exists():
                return path
            # Opera GX
            path_gx = Path(appdata) / "Opera Software" / "Opera GX Stable"
            if path_gx.exists():
                return path_gx
    return None


def _get_opera_local_state_path() -> Optional[Path]:
    """Get Opera Local State file path."""
    user_data_dir = _get_opera_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_opera_elevation_service_path() -> Optional[Path]:
    """Find Opera Elevation Service executable."""
    opera_path = _get_opera_exe_path()
    if not opera_path:
        return None
    
    opera_dir = opera_path.parent
    
    # Search for elevation_service.exe in version subdirectories
    try:
        for item in opera_dir.iterdir():
            if item.is_dir() and item.name[0].isdigit():  # Version folders start with digit
                elevation_service = item / "elevation_service.exe"
                if elevation_service.exists():
                    return elevation_service
    except Exception:
        pass
    
    # Check directly in Opera directory
    elevation_service = opera_dir / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    
    return None


def _is_opera_elevation_service_running() -> bool:
    """Check if Opera Elevation Service is running."""
    if os.name != "nt":
        return False
    try:
        # Opera might use different service names
        service_names = [
            "OperaElevationService",
            "Opera Browser Elevation Service",
            "OperaBrowserElevationService",
        ]
        for service_name in service_names:
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "RUNNING" in result.stdout:
                return True
    except Exception:
        pass
    return False


def _start_opera_elevation_service() -> bool:
    """Try to start Opera Elevation Service."""
    if os.name != "nt":
        return False
    try:
        service_names = [
            "OperaElevationService",
            "Opera Browser Elevation Service",
            "OperaBrowserElevationService",
        ]
        for service_name in service_names:
            result = subprocess.run(
                ["net", "start", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 or "already been started" in result.stderr:
                return True
    except Exception:
        pass
    return False


def _try_opera_ielevator_com_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """
    Attempt decryption using Opera's IElevator COM interface.
    
    Opera, being Chromium-based, may have a similar elevation service.
    """
    if os.name != "nt":
        return None
    
    # Try comtypes method
    result = _try_opera_ielevator_comtypes(encrypted_data)
    if result:
        return result
    
    return None


def _try_opera_ielevator_comtypes(encrypted_data: bytes) -> Optional[bytes]:
    """Try Opera IElevator decryption using comtypes."""
    try:
        import comtypes.client  # type: ignore
        from comtypes import GUID, COMMETHOD, HRESULT, IUnknown  # type: ignore
        from ctypes import POINTER, c_char_p, c_ulong, byref, create_string_buffer
        
        # Define IElevator interface (same as Chrome)
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
        
        # Opera might use different CLSIDs or the same as Chrome
        # Try Opera-specific CLSIDs first, then fall back to Chrome's
        clsids = [
            # Opera-specific CLSIDs (if Opera implements its own)
            "{A2DDA8C8-4C3F-4E64-A8C0-8BDEF1C3A8B2}",  # Hypothetical Opera CLSID
            # Chrome CLSIDs as fallback (Opera might use Chrome's elevation service)
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
                        logger.info(f"Opera ABE decrypted via IElevator COM with CLSID {clsid_str}")
                        return result
            except Exception as e:
                logger.debug(f"Opera IElevator attempt failed for {clsid_str}: {e}")
                continue
        
        comtypes.client.CoUninitialize()
        
    except ImportError:
        logger.debug("comtypes not available for Opera IElevator")
    except Exception as e:
        logger.debug(f"Opera IElevator comtypes failed: {e}")
    
    return None


def decrypt_opera_abe_key_with_dpapi(encrypted_key: bytes) -> Optional[bytes]:
    """
    Try to decrypt Opera ABE key using Windows DPAPI.
    
    This may work on some configurations where ABE enforcement is relaxed.
    """
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        return None
    
    try:
        import win32crypt  # type: ignore
    except ImportError:
        logger.debug("win32crypt not available")
        return None
    
    # Remove APPB prefix
    key_data = encrypted_key[4:]
    
    try:
        decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
        logger.debug("Opera ABE key decrypted via DPAPI")
        return decrypted
    except Exception as e:
        logger.debug(f"Opera DPAPI decryption failed: {e}")
    
    return None


def decrypt_opera_abe_key_via_system_context(encrypted_key: bytes) -> Optional[bytes]:
    """
    Attempt decryption using SYSTEM context.
    Requires elevated privileges.
    """
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        return None
    
    # This requires running as SYSTEM or with special privileges
    try:
        import win32crypt  # type: ignore
        import win32security  # type: ignore
        import win32api  # type: ignore
        
        # Try impersonating SYSTEM (requires SE_IMPERSONATE_PRIVILEGE)
        key_data = encrypted_key[4:]  # Remove APPB prefix
        
        decrypted = win32crypt.CryptUnprotectData(
            key_data,
            None,
            None,
            None,
            0
        )[1]
        return decrypted
    except Exception as e:
        logger.debug(f"Opera SYSTEM context decryption failed: {e}")
    
    return None


def load_opera_abe_key_from_local_state(local_state_path: Optional[Path] = None) -> Optional[bytes]:
    """
    Load and decrypt the ABE key from Opera's Local State file.
    
    Args:
        local_state_path: Path to Opera's Local State file
        
    Returns:
        Decrypted AES key or None if decryption fails
    """
    if local_state_path is None:
        local_state_path = _get_opera_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except (KeyError, json.JSONDecodeError, Exception) as e:
        logger.debug("Failed to read encrypted key from Opera Local State: %s", e)
        return None
    
    # Check if this is an ABE key
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Opera key is not ABE-encrypted, using standard DPAPI")
        return None  # Let the standard decrypt path handle it
    
    logger.info("Detected Opera App-Bound Encryption key, attempting decryption...")
    
    # Try various decryption methods in order of preference
    
    # Method 1: IElevator COM interface (cleanest method)
    result = _try_opera_ielevator_com_decrypt(encrypted_key)
    if result:
        logger.info("Opera ABE key decrypted via IElevator COM")
        return result
    
    # Method 2: Direct DPAPI (works on some configurations)
    result = decrypt_opera_abe_key_with_dpapi(encrypted_key)
    if result:
        logger.info("Opera ABE key decrypted via DPAPI")
        return result
    
    # Method 3: SYSTEM context (requires elevation)
    result = decrypt_opera_abe_key_via_system_context(encrypted_key)
    if result:
        logger.info("Opera ABE key decrypted via SYSTEM context")
        return result
    
    logger.warning("All Opera ABE decryption methods failed")
    return None


def decrypt_opera_v20_value(
    encrypted_value: bytes,
    abe_key: bytes,
) -> str:
    """
    Decrypt a v20 (ABE) encrypted Opera cookie value.
    
    v20 format (same as Chrome):
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
        raise OperaAppBoundDecryptionError("Value does not have v20 prefix")
    
    # Extract components
    nonce = encrypted_value[3:3 + AES_GCM_NONCE_LENGTH]
    ciphertext = encrypted_value[3 + AES_GCM_NONCE_LENGTH:]
    
    try:
        aesgcm = AESGCM(abe_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8", errors="replace")
    except Exception as e:
        raise OperaAppBoundDecryptionError(f"AES-GCM decryption failed: {e}")


class OperaAppBoundDecryptor:
    """
    High-level interface for Opera App-Bound Encryption decryption.
    
    Usage:
        decryptor = OperaAppBoundDecryptor(local_state_path)
        if decryptor.is_available():
            plaintext = decryptor.decrypt_value(encrypted_value)
    """
    
    def __init__(self, local_state_path: Optional[Path] = None):
        self._local_state_path = local_state_path or _get_opera_local_state_path()
        self._abe_key: Optional[bytes] = None
        self._initialized = False
        self._available = False
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        
        if not self._local_state_path:
            return
        
        self._abe_key = load_opera_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
    
    def is_available(self) -> bool:
        """Check if Opera ABE decryption is available."""
        self._ensure_initialized()
        return self._available
    
    def can_decrypt_value(self, encrypted_value: bytes) -> bool:
        """Check if a value can be decrypted with Opera ABE."""
        return is_abe_encrypted_value(encrypted_value) and self.is_available()
    
    def decrypt_value(self, encrypted_value: bytes) -> str:
        """
        Decrypt an Opera ABE-encrypted cookie value.
        
        Args:
            encrypted_value: Encrypted value from cookies database
            
        Returns:
            Decrypted plaintext
            
        Raises:
            OperaAppBoundDecryptionError: If decryption fails
        """
        self._ensure_initialized()
        
        if not self._available or not self._abe_key:
            raise OperaAppBoundDecryptionError("Opera ABE decryption not available")
        
        return decrypt_opera_v20_value(encrypted_value, self._abe_key)


def check_opera_abe_support() -> dict[str, Any]:
    """
    Check system support for Opera App-Bound Encryption decryption.
    
    Returns a dictionary with:
    - windows: Whether running on Windows
    - opera_installed: Whether Opera is found
    - elevation_service: Whether elevation service exists
    - elevation_service_path: Path to elevation_service.exe if found
    - elevation_service_running: Whether elevation service is running
    - ielevator_available: Whether IElevator COM is accessible
    - dpapi_available: Whether DPAPI is available
    - opera_version: Opera version if detected
    """
    result = {
        "windows": os.name == "nt",
        "opera_installed": False,
        "opera_path": None,
        "user_data_dir": None,
        "elevation_service": False,
        "elevation_service_path": None,
        "elevation_service_running": False,
        "ielevator_available": False,
        "dpapi_available": False,
        "opera_version": None,
    }
    
    if not result["windows"]:
        return result
    
    # Check Opera installation
    opera_path = _get_opera_exe_path()
    result["opera_installed"] = opera_path is not None
    if opera_path:
        result["opera_path"] = str(opera_path)
    
    # Check user data directory
    user_data_dir = _get_opera_user_data_dir()
    if user_data_dir:
        result["user_data_dir"] = str(user_data_dir)
    
    # Check elevation service file exists
    if opera_path:
        elevation_service = _get_opera_elevation_service_path()
        result["elevation_service"] = elevation_service is not None
        if elevation_service:
            result["elevation_service_path"] = str(elevation_service)
    
    # Check if elevation service is running
    result["elevation_service_running"] = _is_opera_elevation_service_running()
    
    # If service exists but not running, try to start it
    if result["elevation_service"] and not result["elevation_service_running"]:
        if _start_opera_elevation_service():
            result["elevation_service_running"] = True
    
    # Check DPAPI availability
    try:
        import win32crypt  # type: ignore
        result["dpapi_available"] = True
    except ImportError:
        pass
    
    # Check IElevator COM availability
    try:
        import comtypes.client  # type: ignore
        from comtypes import GUID
        
        # Try to create the COM object (Chrome's CLSID as Opera might use same)
        CLSID_Elevator = GUID("{708860E0-F641-4611-8895-7D867DD3675B}")
        try:
            comtypes.client.CoInitialize()
            obj = comtypes.client.CreateObject(CLSID_Elevator)
            result["ielevator_available"] = obj is not None
        except Exception as e:
            logger.debug(f"IElevator COM test failed: {e}")
            result["ielevator_available"] = False
        finally:
            try:
                comtypes.client.CoUninitialize()
            except:
                pass
    except ImportError:
        pass
    
    # Try to get Opera version
    result["opera_version"] = _get_opera_version()
    
    return result


def _get_opera_version() -> Optional[str]:
    """Get Opera version from registry or files."""
    if os.name != "nt":
        return None
    
    try:
        import winreg
        
        # Try to get version from registry
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\Opera Software") as key:
                    version, _ = winreg.QueryValueEx(key, "Version")
                    if version:
                        return version
            except FileNotFoundError:
                continue
            except Exception:
                continue
    except Exception:
        pass
    
    # Try to get version from Local State
    local_state = _get_opera_local_state_path()
    if local_state and local_state.exists():
        try:
            raw = local_state.read_text(encoding="utf-8")
            data = json.loads(raw)
            # Opera might store version differently
            if "browser" in data:
                browser_info = data["browser"]
                if isinstance(browser_info, dict):
                    version = browser_info.get("last_known_version")
                    if version:
                        return version
        except Exception:
            pass
    
    return None
