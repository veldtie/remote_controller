"""
App-Bound Encryption (ABE) module for Chrome 127+ cookie decryption.

This is the new integrated ABE module that uses native C++ implementation
when available (via pybind11), with fallback to pure Python implementation.

Chrome 127+ uses App-Bound Encryption which ties encryption keys to the Chrome
application itself using Windows Data Protection API with application-specific
contexts. This module provides methods to decrypt such protected data.

Key concepts:
1. ABE wraps the DPAPI key with an additional layer tied to the Chrome executable
2. The encrypted_key in Local State starts with "APPB" prefix for ABE keys
3. Decryption requires either running as Chrome or using IElevator COM interface

Native module based on Alexander 'xaitax' Hagenah's Chrome ABE research:
https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption

References:
- https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- Chrome source: components/os_crypt/sync/os_crypt_win.cc
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

# Try to import native module
try:
    from .abe_native import (
        is_native_available,
        is_abe_encrypted_key as native_is_abe_encrypted_key,
        is_abe_encrypted_value as native_is_abe_encrypted_value,
        decrypt_aes_gcm as native_decrypt_aes_gcm,
        Elevator as NativeElevator,
        BrowserType,
    )
    _native_available = is_native_available()
except ImportError:
    _native_available = False
    
    class BrowserType:
        CHROME = "chrome"
        CHROME_BETA = "chrome_beta"
        CHROME_DEV = "chrome_dev"
        CHROME_CANARY = "chrome_canary"
        EDGE = "edge"
        EDGE_BETA = "edge_beta"
        EDGE_DEV = "edge_dev"
        EDGE_CANARY = "edge_canary"
        BRAVE = "brave"
        BRAVE_BETA = "brave_beta"
        BRAVE_NIGHTLY = "brave_nightly"
        AVAST = "avast"
        OPERA = "opera"
        VIVALDI = "vivaldi"

# Import cryptography for fallback
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _crypto_available = True
except ImportError:
    _crypto_available = False
    AESGCM = None

from .errors import CookieExportError

# ABE-specific constants
ABE_PREFIX = b"APPB"  # App-Bound prefix in encrypted key
V20_PREFIX = b"v20"   # Chrome 127+ uses v20 for ABE-encrypted values
DPAPI_PREFIX = b"DPAPI"

# AES-GCM parameters
AES_GCM_NONCE_LENGTH = 12
AES_GCM_TAG_LENGTH = 16

# Cookie header size (Chrome adds a 32-byte header to decrypted cookie values)
COOKIE_HEADER_SIZE = 32


class AppBoundDecryptionError(CookieExportError):
    """Raised when App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("abe_decryption_failed", message)


def is_abe_encrypted_key(encrypted_key: bytes) -> bool:
    """Check if the key uses App-Bound Encryption (APPB prefix)."""
    if _native_available:
        return native_is_abe_encrypted_key(encrypted_key)
    return encrypted_key.startswith(ABE_PREFIX)


def is_abe_encrypted_value(encrypted_value: bytes) -> bool:
    """Check if a cookie value uses ABE encryption (v20 prefix)."""
    if _native_available:
        return native_is_abe_encrypted_value(encrypted_value)
    return encrypted_value.startswith(V20_PREFIX)


def _get_chrome_exe_path() -> Optional[Path]:
    """Find Chrome executable path."""
    if os.name != "nt":
        return None
    possible_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return None


def _get_chrome_user_data_dir() -> Optional[Path]:
    """Get Chrome User Data directory."""
    if os.name != "nt":
        return None
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        path = Path(local_app_data) / "Google" / "Chrome" / "User Data"
        if path.exists():
            return path
    return None


def _get_chrome_local_state_path() -> Optional[Path]:
    """Get Chrome Local State file path."""
    user_data_dir = _get_chrome_user_data_dir()
    if user_data_dir:
        local_state = user_data_dir / "Local State"
        if local_state.exists():
            return local_state
    return None


def _get_elevation_service_path() -> Optional[Path]:
    """Find Chrome Elevation Service executable."""
    chrome_path = _get_chrome_exe_path()
    if not chrome_path:
        return None
    
    chrome_app_dir = chrome_path.parent  # .../Application/
    
    try:
        for item in chrome_app_dir.iterdir():
            if item.is_dir() and item.name[0].isdigit():
                elevation_service = item / "elevation_service.exe"
                if elevation_service.exists():
                    return elevation_service
    except Exception:
        pass
    
    elevation_service = chrome_app_dir / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    
    return None


def _is_elevation_service_running() -> bool:
    """Check if Chrome Elevation Service is running."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["sc", "query", "GoogleChromeElevationService"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "RUNNING" in result.stdout
    except Exception:
        return False


def _start_elevation_service() -> bool:
    """Try to start Chrome Elevation Service."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["net", "start", "GoogleChromeElevationService"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 or "already been started" in result.stderr
    except Exception:
        return False


def decrypt_abe_key(
    encrypted_key: bytes,
    browser_type: str = BrowserType.CHROME,
    auto_detect: bool = True
) -> Optional[bytes]:
    """
    Decrypt App-Bound Encryption key using IElevator COM interface.
    
    This uses the native C++ implementation when available for better
    performance and reliability.
    
    Args:
        encrypted_key: APPB-prefixed encrypted key from Local State
        browser_type: Browser type for elevation service
        auto_detect: If True, try all available browsers automatically
        
    Returns:
        Decrypted key bytes or None on failure
    """
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Key is not ABE-encrypted")
        return None
    
    try:
        if _native_available:
            elevator = NativeElevator()
            if auto_detect:
                result = elevator.decrypt_key_auto(encrypted_key)
            else:
                result = elevator.decrypt_key(encrypted_key, browser_type)
            
            if result.get("success"):
                logger.info("ABE key decrypted via native IElevator")
                return result.get("data")
            else:
                logger.warning(f"Native IElevator failed: {result.get('error')}")
        else:
            # Try Python COM fallback
            result = _python_ielevator_decrypt(encrypted_key, browser_type, auto_detect)
            if result:
                logger.info("ABE key decrypted via Python IElevator")
                return result
    except Exception as e:
        logger.error(f"ABE key decryption failed: {e}")
    
    return None


def _python_ielevator_decrypt(
    encrypted_key: bytes,
    browser_type: str,
    auto_detect: bool
) -> Optional[bytes]:
    """Python COM fallback for IElevator decryption."""
    if os.name != "nt":
        return None
    
    try:
        import comtypes.client
        from comtypes import GUID
        
        # Browser CLSIDs
        clsids = {
            BrowserType.CHROME: "{708860E0-F641-4611-8895-7D867DD3675B}",
            BrowserType.CHROME_BETA: "{DD2646BA-3707-4BF8-B9A7-038691A68FC2}",
            BrowserType.CHROME_DEV: "{DA7FDCA5-2CAA-4637-AA17-0749F64F49D2}",
            BrowserType.CHROME_CANARY: "{3A84F9C2-6164-485C-A7D9-4B27F8AC3D58}",
            BrowserType.EDGE: "{1EBBCAB8-D9A8-4FBA-8BC2-7B7687B31B52}",
            BrowserType.BRAVE: "{576B31AF-6369-4B6B-8560-E4B203A97A8B}",
            BrowserType.AVAST: "{30D7F8EB-1F8E-4D77-A15E-C93C342AE54D}",
        }
        
        browsers_to_try = list(clsids.keys()) if auto_detect else [browser_type]
        
        for browser in browsers_to_try:
            clsid_str = clsids.get(browser)
            if not clsid_str:
                continue
            
            try:
                comtypes.client.CoInitialize()
                clsid = GUID(clsid_str)
                obj = comtypes.client.CreateObject(clsid)
                
                if hasattr(obj, 'DecryptData'):
                    # Try BSTR-based interface
                    from ctypes import create_string_buffer, byref, c_ulong
                    import ctypes.wintypes as wintypes
                    
                    result = obj.DecryptData(encrypted_key)
                    if result:
                        return bytes(result)
                        
            except Exception as e:
                logger.debug(f"Python COM {browser} failed: {e}")
            finally:
                try:
                    comtypes.client.CoUninitialize()
                except:
                    pass
                    
    except ImportError:
        logger.debug("comtypes not available for Python COM fallback")
    except Exception as e:
        logger.debug(f"Python IElevator failed: {e}")
    
    return None


def decrypt_abe_value(
    encrypted_value: bytes,
    abe_key: bytes,
    strip_header: bool = False
) -> Optional[str]:
    """
    Decrypt a v20 (ABE) encrypted value using AES-GCM.
    
    Args:
        encrypted_value: Data with v20 prefix + IV + ciphertext + tag
        abe_key: 32-byte AES key from decrypt_abe_key()
        strip_header: If True, remove Chrome's 32-byte cookie header.
                     NOTE: For standard cookie values, this should be False.
                     Only certain Chrome internal encrypted data uses headers.
        
    Returns:
        Decrypted string or None on failure
    """
    if not is_abe_encrypted_value(encrypted_value):
        logger.debug("Value does not have v20 prefix")
        return None
    
    if not abe_key or len(abe_key) != 32:
        logger.debug("Invalid ABE key: must be 32 bytes for AES-256")
        return None
    
    try:
        if _native_available:
            result = native_decrypt_aes_gcm(abe_key, encrypted_value)
            if result:
                if strip_header and len(result) > COOKIE_HEADER_SIZE:
                    result = result[COOKIE_HEADER_SIZE:]
                return result.decode("utf-8", errors="replace")
        
        # Python fallback
        if _crypto_available:
            nonce = encrypted_value[3:3 + AES_GCM_NONCE_LENGTH]
            ciphertext = encrypted_value[3 + AES_GCM_NONCE_LENGTH:]
            
            aesgcm = AESGCM(abe_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            if strip_header and len(plaintext) > COOKIE_HEADER_SIZE:
                plaintext = plaintext[COOKIE_HEADER_SIZE:]
            
            return plaintext.decode("utf-8", errors="replace")
            
    except Exception as e:
        logger.debug(f"AES-GCM decryption failed: {e}")
    
    return None


def decrypt_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """
    Decrypt a v20 (ABE) encrypted value using AES-GCM.
    
    This is a convenience function that raises AppBoundDecryptionError on failure,
    unlike decrypt_abe_value which returns None.
    
    Args:
        encrypted_value: Data with v20 prefix + IV + ciphertext + tag
        abe_key: 32-byte AES key from decrypt_abe_key()
        
    Returns:
        Decrypted string
        
    Raises:
        AppBoundDecryptionError: If decryption fails
    """
    if not is_abe_encrypted_value(encrypted_value):
        raise AppBoundDecryptionError("Value does not have v20 prefix")
    
    if not abe_key or len(abe_key) != 32:
        raise AppBoundDecryptionError("Invalid ABE key: must be 32 bytes for AES-256")
    
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=False)
    if result is None:
        raise AppBoundDecryptionError("AES-GCM decryption failed")
    
    return result


def load_abe_key_from_local_state(local_state_path: Optional[Path] = None) -> Optional[bytes]:
    """
    Load and decrypt ABE key from Chrome's Local State file.
    
    Args:
        local_state_path: Path to Local State file (auto-detected if None)
        
    Returns:
        Decrypted ABE key or None
    """
    if local_state_path is None:
        local_state_path = _get_chrome_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        # Remove DPAPI prefix if present
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            return decrypt_abe_key(encrypted_key, auto_detect=True)
        else:
            # Not ABE, try DPAPI
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load ABE key: {e}")
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


def decrypt_abe_key_with_dpapi(encrypted_key: bytes) -> Optional[bytes]:
    """
    Attempt to decrypt an ABE key using DPAPI directly.
    
    This is a fallback method that may work on some configurations
    where ABE enforcement is relaxed or when running as the same user.
    
    Args:
        encrypted_key: APPB-prefixed encrypted key from Local State
        
    Returns:
        Decrypted key bytes or None on failure
    """
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Key is not ABE-encrypted")
        return None
    
    # Remove APPB prefix
    key_data = encrypted_key[4:]
    
    try:
        import win32crypt
        
        # Method 1: Direct DPAPI
        try:
            decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
            if decrypted and len(decrypted) == 32:  # AES-256 key should be 32 bytes
                logger.info("ABE key decrypted via direct DPAPI")
                return decrypted
        except Exception as e:
            logger.debug(f"Direct DPAPI failed: {e}")
        
        # Method 2: Try with CRYPTPROTECT_UI_FORBIDDEN flag
        try:
            CRYPTPROTECT_UI_FORBIDDEN = 0x01
            decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, CRYPTPROTECT_UI_FORBIDDEN)[1]
            if decrypted and len(decrypted) == 32:
                logger.info("ABE key decrypted via DPAPI (UI_FORBIDDEN)")
                return decrypted
        except Exception:
            pass
        
        # Method 3: Try with LOCAL_MACHINE flag
        try:
            CRYPTPROTECT_LOCAL_MACHINE = 0x04
            decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, CRYPTPROTECT_LOCAL_MACHINE)[1]
            if decrypted and len(decrypted) == 32:
                logger.info("ABE key decrypted via DPAPI (LOCAL_MACHINE)")
                return decrypted
        except Exception:
            pass
        
        # Method 4: Try decrypting full key with APPB prefix
        try:
            decrypted = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
            if decrypted and len(decrypted) == 32:
                logger.info("ABE key decrypted via full key DPAPI")
                return decrypted
        except Exception:
            pass
        
    except ImportError:
        logger.debug("win32crypt not available")
    except Exception as e:
        logger.debug(f"DPAPI ABE key decryption failed: {e}")
    
    return None


def _try_ielevator_com_decrypt(encrypted_key: bytes) -> Optional[bytes]:
    """
    Attempt to decrypt an ABE key using Chrome's IElevator COM interface.
    
    This is the primary method for decrypting ABE keys on Chrome 127+.
    It uses the elevation service's COM interface to access the app-bound key.
    
    Args:
        encrypted_key: APPB-prefixed encrypted key from Local State
        
    Returns:
        Decrypted key bytes or None on failure
    """
    if os.name != "nt":
        return None
    
    if not is_abe_encrypted_key(encrypted_key):
        logger.debug("Key is not ABE-encrypted")
        return None
    
    # Try native module first
    if _native_available:
        try:
            elevator = NativeElevator()
            result = elevator.decrypt_key_auto(encrypted_key)
            if result.get("success"):
                logger.info("ABE key decrypted via native IElevator")
                return result.get("data")
        except Exception as e:
            logger.debug(f"Native IElevator failed: {e}")
    
    # Fall back to Python COM implementation
    return _python_ielevator_decrypt(encrypted_key, BrowserType.CHROME, auto_detect=True)


class AppBoundDecryptor:
    """
    High-level interface for App-Bound Encryption decryption.
    
    Provides a unified API for decrypting ABE-protected browser data
    using native C++ implementation when available.
    """
    
    def __init__(
        self,
        local_state_path: Optional[Path] = None,
        browser_type: str = BrowserType.CHROME
    ):
        """
        Initialize ABE decryptor.
        
        Args:
            local_state_path: Path to Local State file (auto-detected if None)
            browser_type: Browser type for elevation service selection
        """
        self._local_state_path = local_state_path
        self._browser_type = browser_type
        self._abe_key: Optional[bytes] = None
        self._initialized = False
        self._available = False
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of ABE key."""
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("ABE decryptor initialized successfully")
        else:
            logger.warning("ABE decryptor initialization failed - key not available")
    
    @property
    def is_available(self) -> bool:
        """Check if ABE decryption is available."""
        self._ensure_initialized()
        return self._available
    
    @property
    def abe_key(self) -> Optional[bytes]:
        """Get the decrypted ABE key."""
        self._ensure_initialized()
        return self._abe_key
    
    def can_decrypt_value(self, encrypted_value: bytes) -> bool:
        """Check if a value can be decrypted."""
        return is_abe_encrypted_value(encrypted_value) and self.is_available
    
    def decrypt_value(
        self,
        encrypted_value: bytes,
        strip_header: bool = False
    ) -> Optional[str]:
        """
        Decrypt an ABE-encrypted value.
        
        Args:
            encrypted_value: v20-prefixed encrypted data
            strip_header: Remove Chrome's 32-byte header (usually False for cookies)
            
        Returns:
            Decrypted string or None
        """
        self._ensure_initialized()
        
        if not self._available or not self._abe_key:
            raise AppBoundDecryptionError("ABE key not available")
        
        result = decrypt_abe_value(encrypted_value, self._abe_key, strip_header)
        if result is None:
            raise AppBoundDecryptionError("Decryption failed")
        
        return result
    
    def decrypt_value_safe(
        self,
        encrypted_value: bytes,
        strip_header: bool = False
    ) -> Optional[str]:
        """
        Safely decrypt a value, returning None instead of raising.
        
        Args:
            encrypted_value: v20-prefixed encrypted data
            strip_header: Remove Chrome's 32-byte header (usually False for cookies)
            
        Returns:
            Decrypted string or None
        """
        try:
            return self.decrypt_value(encrypted_value, strip_header)
        except AppBoundDecryptionError:
            return None


class CDPCookieExtractor:
    """
    Cookie extractor using Chrome DevTools Protocol.
    
    This is the recommended method for Chrome 127+ as CDP provides
    already-decrypted cookie values.
    """
    
    def __init__(
        self,
        browser_path: Optional[Path] = None,
        user_data_dir: Optional[Path] = None,
        debug_port: int = 9222
    ):
        """
        Initialize CDP extractor.
        
        Args:
            browser_path: Path to browser executable
            user_data_dir: User data directory
            debug_port: Remote debugging port
        """
        self._browser_path = browser_path or _get_chrome_exe_path()
        self._user_data_dir = user_data_dir or _get_chrome_user_data_dir()
        self._debug_port = debug_port
        self._process = None
        self._temp_profile_dir = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()
    
    def _cleanup(self):
        """Cleanup browser process and temp files."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        
        if self._temp_profile_dir:
            try:
                import shutil
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_profile_dir = None
    
    def get_all_cookies(self) -> List[Dict[str, Any]]:
        """
        Get all cookies from the browser.
        
        Returns:
            List of cookie dictionaries
        """
        if not self._browser_path or not self._browser_path.exists():
            logger.warning("Browser executable not found")
            return []
        
        try:
            # Create temp profile directory
            self._temp_profile_dir = tempfile.mkdtemp(prefix="chrome_cdp_")
            
            # Start browser with remote debugging
            cmd = [
                str(self._browser_path),
                f"--remote-debugging-port={self._debug_port}",
                f"--user-data-dir={self._user_data_dir or self._temp_profile_dir}",
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Wait for browser to start
            import time
            time.sleep(2)
            
            # Connect to CDP and get cookies
            return self._get_cookies_via_cdp()
            
        except Exception as e:
            logger.error(f"CDP cookie extraction failed: {e}")
            return []
    
    def _get_cookies_via_cdp(self) -> List[Dict[str, Any]]:
        """Connect to CDP and retrieve cookies."""
        try:
            import json
            import urllib.request
            
            # Get CDP endpoints
            url = f"http://127.0.0.1:{self._debug_port}/json"
            with urllib.request.urlopen(url, timeout=5) as response:
                targets = json.loads(response.read())
            
            if not targets:
                return []
            
            # Get WebSocket URL
            ws_url = targets[0].get("webSocketDebuggerUrl")
            if not ws_url:
                return []
            
            # Connect via WebSocket
            try:
                import websocket
                ws = websocket.create_connection(ws_url)
            except ImportError:
                try:
                    import websockets
                    import asyncio
                    return asyncio.get_event_loop().run_until_complete(
                        self._get_cookies_async(ws_url)
                    )
                except ImportError:
                    logger.warning("No WebSocket library available")
                    return []
            
            # Send command to get all cookies
            request = {
                "id": 1,
                "method": "Network.getAllCookies",
            }
            ws.send(json.dumps(request))
            
            # Receive response
            response = json.loads(ws.recv())
            ws.close()
            
            if "result" in response and "cookies" in response["result"]:
                return response["result"]["cookies"]
            
            return []
            
        except Exception as e:
            logger.debug(f"CDP connection failed: {e}")
            return []
    
    async def _get_cookies_async(self, ws_url: str) -> List[Dict[str, Any]]:
        """Async WebSocket connection using websockets library."""
        import websockets
        import json
        
        async with websockets.connect(ws_url) as ws:
            request = {
                "id": 1,
                "method": "Network.getAllCookies",
            }
            await ws.send(json.dumps(request))
            response = json.loads(await ws.recv())
            
            if "result" in response and "cookies" in response["result"]:
                return response["result"]["cookies"]
        
        return []


def check_abe_support() -> Dict[str, Any]:
    """
    Check system support for App-Bound Encryption decryption.
    
    Returns:
        Dictionary with support status information
    """
    result = {
        "windows": os.name == "nt",
        "native_module": _native_available,
        "crypto_available": _crypto_available,
        "chrome_installed": False,
        "chrome_path": None,
        "user_data_dir": None,
        "elevation_service": False,
        "elevation_service_path": None,
        "elevation_service_running": False,
        "ielevator_available": False,
        "dpapi_available": False,
        "cdp_available": False,
        "recommended_method": None,
    }
    
    if not result["windows"]:
        result["recommended_method"] = "unsupported_platform"
        return result
    
    # Check Chrome installation
    chrome_path = _get_chrome_exe_path()
    result["chrome_installed"] = chrome_path is not None
    if chrome_path:
        result["chrome_path"] = str(chrome_path)
    
    user_data_dir = _get_chrome_user_data_dir()
    if user_data_dir:
        result["user_data_dir"] = str(user_data_dir)
    
    # Check elevation service
    if chrome_path:
        elevation_service = _get_elevation_service_path()
        result["elevation_service"] = elevation_service is not None
        if elevation_service:
            result["elevation_service_path"] = str(elevation_service)
    
    result["elevation_service_running"] = _is_elevation_service_running()
    
    # Check DPAPI availability
    try:
        import win32crypt
        result["dpapi_available"] = True
    except ImportError:
        pass
    
    # Check IElevator availability (native or Python COM)
    if _native_available:
        result["ielevator_available"] = True
    else:
        try:
            import comtypes.client
            result["ielevator_available"] = True
        except ImportError:
            pass
    
    # Check CDP availability
    if result["chrome_installed"]:
        try:
            import websocket
            result["cdp_available"] = True
        except ImportError:
            try:
                import websockets
                result["cdp_available"] = True
            except ImportError:
                pass
    
    # Determine recommended method
    if _native_available and result["ielevator_available"]:
        result["recommended_method"] = "native_ielevator"
    elif result["cdp_available"]:
        result["recommended_method"] = "cdp"
    elif result["ielevator_available"]:
        result["recommended_method"] = "ielevator"
    elif result["dpapi_available"]:
        result["recommended_method"] = "dpapi"
    else:
        result["recommended_method"] = "none"
    
    return result


def get_abe_decryption_status_message() -> str:
    """Get a human-readable status message about ABE decryption capabilities."""
    support = check_abe_support()
    
    if not support["windows"]:
        return "ABE decryption is only supported on Windows."
    
    if not support["chrome_installed"]:
        return "Chrome is not installed. ABE decryption requires Chrome."
    
    messages = []
    
    if support["native_module"]:
        messages.append("✓ Native ABE module available (best performance)")
    else:
        messages.append("✗ Native ABE module not available (using Python fallback)")
    
    if support["cdp_available"]:
        messages.append("✓ CDP extraction available (recommended for Chrome 127+)")
    else:
        messages.append("✗ CDP extraction not available (install websocket-client)")
    
    if support["ielevator_available"]:
        messages.append("✓ IElevator COM interface available")
    else:
        messages.append("✗ IElevator COM not accessible")
    
    if support["dpapi_available"]:
        messages.append("✓ DPAPI available (limited for ABE)")
    else:
        messages.append("✗ DPAPI not available")
    
    messages.append(f"\nRecommended method: {support['recommended_method'].upper()}")
    
    return "\n".join(messages)


# Convenience functions for backwards compatibility
def try_cdp_cookie_extraction(browser_name: str = "chrome") -> Tuple[bool, List[Dict]]:
    """
    Attempt to extract cookies using CDP.
    
    Returns:
        Tuple of (success, cookies)
    """
    try:
        browser_path = _get_chrome_exe_path()
        if not browser_path:
            return False, []
        
        with CDPCookieExtractor(browser_path) as extractor:
            cookies = extractor.get_all_cookies()
            if cookies:
                logger.info(f"CDP extraction successful: {len(cookies)} cookies")
                return True, cookies
        
        return False, []
        
    except Exception as e:
        logger.debug(f"CDP extraction failed: {e}")
        return False, []


def get_cookies_via_cdp(
    chrome_path: Optional[Path] = None,
    user_data_dir: Optional[Path] = None,
) -> List[Dict]:
    """
    Get decrypted cookies using Chrome DevTools Protocol.
    
    Args:
        chrome_path: Path to Chrome executable
        user_data_dir: Chrome user data directory
        
    Returns:
        List of cookie dictionaries
    """
    with CDPCookieExtractor(chrome_path, user_data_dir) as extractor:
        return extractor.get_all_cookies()


# Export public API
__all__ = [
    # Classes
    "AppBoundDecryptionError",
    "AppBoundDecryptor",
    "CDPCookieExtractor",
    "BrowserType",
    # Functions
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "decrypt_abe_key",
    "decrypt_abe_value",
    "decrypt_v20_value",
    "decrypt_abe_key_with_dpapi",
    "_try_ielevator_com_decrypt",
    "load_abe_key_from_local_state",
    "check_abe_support",
    "get_abe_decryption_status_message",
    "try_cdp_cookie_extraction",
    "get_cookies_via_cdp",
    # Constants
    "ABE_PREFIX",
    "V20_PREFIX",
    "AES_GCM_NONCE_LENGTH",
]
