"""
App-Bound Encryption (ABE) module for Microsoft Edge browser cookie decryption.

Microsoft Edge is based on Chromium and uses the same App-Bound Encryption mechanism
as Chrome 127+. This module provides methods to decrypt Edge's ABE-protected data.

Key differences from Chrome:
1. Edge stores data in %LOCALAPPDATA%/Microsoft/Edge/User Data/
2. Edge has its own elevation service with Microsoft-specific CLSIDs
3. Edge uses different service names (MicrosoftEdgeElevationService)

References:
- Chrome ABE: https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- Edge is based on Chromium source code
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


class EdgeAppBoundDecryptionError(CookieExportError):
    """Raised when Edge App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("edge_abe_decryption_failed", message)


def is_abe_encrypted_key(encrypted_key: bytes) -> bool:
    """Check if the key uses App-Bound Encryption (APPB prefix)."""
    return encrypted_key.startswith(ABE_PREFIX)


def is_abe_encrypted_value(encrypted_value: bytes) -> bool:
    """Check if a cookie value uses ABE encryption (v20 prefix)."""
    return encrypted_value.startswith(V20_PREFIX)


def _get_edge_exe_path() -> Optional[Path]:
    """Find Microsoft Edge executable path."""
    possible_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
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
                    with winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Edge") as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_path:
                            edge_exe = Path(install_path) / "msedge.exe"
                            if edge_exe.exists():
                                return edge_exe
                except FileNotFoundError:
                    continue
        except Exception:
            pass
    
    return None


def _get_edge_user_data_dir() -> Optional[Path]:
    """Get Edge User Data directory."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            path = Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
            if path.exists():
                return path
    return None


def _get_edge_local_state_path() -> Optional[Path]:
    """Get Edge Local State file path."""
    user_data_dir = _get_edge_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_edge_elevation_service_path() -> Optional[Path]:
    """Find Edge Elevation Service executable."""
    edge_path = _get_edge_exe_path()
    if not edge_path:
        return None
    
    edge_app_dir = edge_path.parent
    
    try:
        for item in edge_app_dir.iterdir():
            if item.is_dir() and item.name[0].isdigit():
                elevation_service = item / "elevation_service.exe"
                if elevation_service.exists():
                    return elevation_service
    except Exception:
        pass
    
    elevation_service = edge_app_dir / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    
    return None


def _is_edge_elevation_service_running() -> bool:
    """Check if Edge Elevation Service is running."""
    if os.name != "nt":
        return False
    try:
        service_names = [
            "MicrosoftEdgeElevationService",
            "edgeupdate",
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


def _start_edge_elevation_service() -> bool:
    """Try to start Edge Elevation Service."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["net", "start", "MicrosoftEdgeElevationService"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 or "already been started" in result.stderr
    except Exception:
        pass
    return False


def _try_edge_ielevator_com_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """Attempt decryption using Edge's IElevator COM interface."""
    if os.name != "nt":
        return None
    
    result = _try_edge_ielevator_comtypes(encrypted_data)
    if result:
        return result
    
    return None


def _try_edge_ielevator_comtypes(encrypted_data: bytes) -> Optional[bytes]:
    """Try Edge IElevator decryption using comtypes."""
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
        
        # Edge-specific CLSIDs
        clsids = [
            "{2E1DD7EF-C12D-4F9C-A80B-2F78A8D87A2A}",  # Edge Stable (hypothetical)
            "{B5977F34-9734-4EE9-BA74-D8A6E69F41A4}",  # Edge Beta (hypothetical)
            # Fallback to Chrome CLSIDs as Edge might use compatible interface
            "{708860E0-F641-4611-8895-7D867DD3675B}",
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
                        logger.info(f"Edge ABE decrypted via IElevator COM with CLSID {clsid_str}")
                        return result
            except Exception as e:
                logger.debug(f"Edge IElevator attempt failed for {clsid_str}: {e}")
                continue
        
        comtypes.client.CoUninitialize()
        
    except ImportError:
        logger.debug("comtypes not available for Edge IElevator")
    except Exception as e:
        logger.debug(f"Edge IElevator comtypes failed: {e}")
    
    return None


def decrypt_edge_abe_key_with_dpapi(encrypted_key: bytes) -> Optional[bytes]:
    """Try to decrypt Edge ABE key using Windows DPAPI."""
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        return None
    
    try:
        import win32crypt
    except ImportError:
        logger.debug("win32crypt not available")
        return None
    
    key_data = encrypted_key[4:]  # Remove APPB prefix
    
    try:
        decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
        logger.debug("Edge ABE key decrypted via DPAPI")
        return decrypted
    except Exception as e:
        logger.debug(f"Edge DPAPI decryption failed: {e}")
    
    return None


def decrypt_edge_abe_key_via_system_context(encrypted_key: bytes) -> Optional[bytes]:
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
        logger.debug(f"Edge SYSTEM context decryption failed: {e}")
    
    return None


def load_edge_abe_key_from_local_state(local_state_path: Optional[Path] = None) -> Optional[bytes]:
    """Load and decrypt the ABE key from Edge's Local State file."""
    if local_state_path is None:
        local_state_path = _get_edge_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except (KeyError, json.JSONDecodeError, Exception) as e:
        logger.debug("Failed to read encrypted key from Edge Local State: %s", e)
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Edge key is not ABE-encrypted, using standard DPAPI")
        return None
    
    logger.info("Detected Edge App-Bound Encryption key, attempting decryption...")
    
    result = _try_edge_ielevator_com_decrypt(encrypted_key)
    if result:
        logger.info("Edge ABE key decrypted via IElevator COM")
        return result
    
    result = decrypt_edge_abe_key_with_dpapi(encrypted_key)
    if result:
        logger.info("Edge ABE key decrypted via DPAPI")
        return result
    
    result = decrypt_edge_abe_key_via_system_context(encrypted_key)
    if result:
        logger.info("Edge ABE key decrypted via SYSTEM context")
        return result
    
    logger.warning("All Edge ABE decryption methods failed")
    return None


def decrypt_edge_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Edge cookie value."""
    if not is_abe_encrypted_value(encrypted_value):
        raise EdgeAppBoundDecryptionError("Value does not have v20 prefix")
    
    nonce = encrypted_value[3:3 + AES_GCM_NONCE_LENGTH]
    ciphertext = encrypted_value[3 + AES_GCM_NONCE_LENGTH:]
    
    try:
        aesgcm = AESGCM(abe_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8", errors="replace")
    except Exception as e:
        raise EdgeAppBoundDecryptionError(f"AES-GCM decryption failed: {e}")


class EdgeAppBoundDecryptor:
    """High-level interface for Edge App-Bound Encryption decryption."""
    
    def __init__(self, local_state_path: Optional[Path] = None):
        self._local_state_path = local_state_path or _get_edge_local_state_path()
        self._abe_key: Optional[bytes] = None
        self._initialized = False
        self._available = False
    
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        if not self._local_state_path:
            return
        self._abe_key = load_edge_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
    
    def is_available(self) -> bool:
        self._ensure_initialized()
        return self._available
    
    def can_decrypt_value(self, encrypted_value: bytes) -> bool:
        return is_abe_encrypted_value(encrypted_value) and self.is_available()
    
    def decrypt_value(self, encrypted_value: bytes) -> str:
        self._ensure_initialized()
        if not self._available or not self._abe_key:
            raise EdgeAppBoundDecryptionError("Edge ABE decryption not available")
        return decrypt_edge_v20_value(encrypted_value, self._abe_key)


def check_edge_abe_support() -> dict[str, Any]:
    """Check system support for Edge App-Bound Encryption decryption."""
    result = {
        "windows": os.name == "nt",
        "edge_installed": False,
        "edge_path": None,
        "user_data_dir": None,
        "elevation_service": False,
        "elevation_service_path": None,
        "elevation_service_running": False,
        "ielevator_available": False,
        "dpapi_available": False,
        "edge_version": None,
    }
    
    if not result["windows"]:
        return result
    
    edge_path = _get_edge_exe_path()
    result["edge_installed"] = edge_path is not None
    if edge_path:
        result["edge_path"] = str(edge_path)
    
    user_data_dir = _get_edge_user_data_dir()
    if user_data_dir:
        result["user_data_dir"] = str(user_data_dir)
    
    if edge_path:
        elevation_service = _get_edge_elevation_service_path()
        result["elevation_service"] = elevation_service is not None
        if elevation_service:
            result["elevation_service_path"] = str(elevation_service)
    
    result["elevation_service_running"] = _is_edge_elevation_service_running()
    
    if result["elevation_service"] and not result["elevation_service_running"]:
        if _start_edge_elevation_service():
            result["elevation_service_running"] = True
    
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
    
    result["edge_version"] = _get_edge_version()
    
    return result


def _get_edge_version() -> Optional[str]:
    """Get Edge version from registry or files."""
    if os.name != "nt":
        return None
    
    try:
        import winreg
        for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Edge\BLBeacon") as key:
                    version, _ = winreg.QueryValueEx(key, "version")
                    if version:
                        return version
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    local_state = _get_edge_local_state_path()
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
