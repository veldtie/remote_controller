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
    
    chrome_app_dir = chrome_path.parent  # .../Application/
    
    # elevation_service.exe is in version subdirectory like 128.0.6613.120/
    # Search in all version directories
    try:
        for item in chrome_app_dir.iterdir():
            if item.is_dir() and item.name[0].isdigit():  # Version folders start with digit
                elevation_service = item / "elevation_service.exe"
                if elevation_service.exists():
                    return elevation_service
    except Exception:
        pass
    
    # Fallback: check directly in Application folder
    elevation_service = chrome_app_dir / "elevation_service.exe"
    if elevation_service.exists():
        return elevation_service
    
    return None


def _is_elevation_service_running() -> bool:
    """Check if Chrome Elevation Service is running."""
    if os.name != "nt":
        return False
    try:
        import subprocess
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
        import subprocess
        result = subprocess.run(
            ["net", "start", "GoogleChromeElevationService"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 or "already been started" in result.stderr
    except Exception:
        return False


def _try_ielevator_com_decrypt(encrypted_data: bytes) -> Optional[bytes]:
    """
    Attempt decryption using Chrome's IElevator COM interface.
    
    This is the official way to decrypt ABE data when not running as Chrome.
    Requires Chrome to be installed and the elevation service to be available.
    """
    if os.name != "nt":
        return None
    
    # Try multiple methods for IElevator decryption
    result = _try_ielevator_ctypes(encrypted_data)
    if result:
        return result
    
    result = _try_ielevator_comtypes(encrypted_data)
    if result:
        return result
    
    return None


def _try_ielevator_ctypes(encrypted_data: bytes) -> Optional[bytes]:
    """Try IElevator decryption using ctypes (no comtypes needed)."""
    try:
        import ctypes
        from ctypes import wintypes
        
        # Load ole32 for COM
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        
        # Google Chrome Elevation Service CLSID
        # Different Chrome channels use different CLSIDs
        clsids = [
            "{708860E0-F641-4611-8895-7D867DD3675B}",  # Chrome Stable
            "{DD2646BA-3707-4BF8-B9A7-038691A68FC2}",  # Chrome Beta  
            "{DA7FDCA5-2CAA-4637-AA17-0749F64F49D2}",  # Chrome Dev
            "{3A84F9C2-6164-485C-A7D9-4B27F8AC3D58}",  # Chrome Canary
        ]
        
        for clsid in clsids:
            try:
                # Try using subprocess to call Chrome's elevation_service directly
                import subprocess
                chrome_paths = [
                    Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application",
                    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application",
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application",
                ]
                
                for chrome_path in chrome_paths:
                    elevation_exe = chrome_path / "elevation_service.exe"
                    if elevation_exe.exists():
                        logger.debug(f"Found elevation service at: {elevation_exe}")
                        break
            except Exception as e:
                logger.debug(f"ctypes IElevator attempt failed for {clsid}: {e}")
                continue
        
        ole32.CoUninitialize()
        
    except Exception as e:
        logger.debug(f"ctypes IElevator failed: {e}")
    
    return None


def _try_ielevator_comtypes(encrypted_data: bytes) -> Optional[bytes]:
    """Try IElevator decryption using comtypes."""
    try:
        import comtypes.client  # type: ignore
        from comtypes import GUID, COMMETHOD, HRESULT, IUnknown  # type: ignore
        from ctypes import POINTER, c_char_p, c_ulong, byref, create_string_buffer
        
        # Define IElevator interface
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
        
        # Chrome Stable CLSID
        CLSID_Elevator = GUID("{708860E0-F641-4611-8895-7D867DD3675B}")
        
        try:
            comtypes.client.CoInitialize()
            elevator = comtypes.client.CreateObject(CLSID_Elevator, interface=IElevator)
            
            plaintext = c_char_p()
            plaintext_len = c_ulong()
            
            hr = elevator.DecryptData(
                encrypted_data,
                len(encrypted_data),
                byref(plaintext),
                byref(plaintext_len)
            )
            
            if hr == 0 and plaintext.value:
                return plaintext.value[:plaintext_len.value]
                
        except Exception as e:
            logger.debug(f"comtypes IElevator failed: {e}")
        finally:
            try:
                comtypes.client.CoUninitialize()
            except:
                pass
                
    except ImportError:
        logger.debug("comtypes not available for IElevator")
    except Exception as e:
        logger.debug(f"comtypes IElevator setup failed: {e}")
    
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


def _try_decrypt_with_chrome_keyring(encrypted_key: bytes) -> Optional[bytes]:
    """
    Alternative method: Try to decrypt ABE key using Chrome's internal keyring.
    
    This works by reading additional encryption context from Chrome's data.
    """
    if os.name != "nt":
        return None
        
    try:
        import win32crypt  # type: ignore
        import win32api  # type: ignore
        import win32security  # type: ignore
        
        # ABE uses application-bound DPAPI with Chrome's SID
        # Try decryption with different entropy values
        if not encrypted_key.startswith(ABE_PREFIX):
            return None
            
        key_data = encrypted_key[len(ABE_PREFIX):]
        
        # Method 1: Try with Chrome's app path as entropy
        chrome_path = _get_chrome_exe_path()
        if chrome_path:
            try:
                entropy = str(chrome_path).encode('utf-16-le')
                decrypted = win32crypt.CryptUnprotectData(
                    key_data, None, entropy, None, 0
                )[1]
                if decrypted and len(decrypted) == 32:  # AES-256 key
                    return decrypted
            except Exception:
                pass
        
        # Method 2: Try with no entropy (user-level protection only)
        try:
            decrypted = win32crypt.CryptUnprotectData(
                key_data, None, None, None, 0
            )[1]
            if decrypted and len(decrypted) >= 16:
                return decrypted
        except Exception:
            pass
            
        # Method 3: Try with CRYPTPROTECT_LOCAL_MACHINE flag
        try:
            CRYPTPROTECT_LOCAL_MACHINE = 0x04
            decrypted = win32crypt.CryptUnprotectData(
                key_data, None, None, None, CRYPTPROTECT_LOCAL_MACHINE
            )[1]
            if decrypted:
                return decrypted
        except Exception:
            pass
            
    except ImportError:
        logger.debug("win32crypt not available for keyring decryption")
    except Exception as e:
        logger.debug(f"Chrome keyring decryption failed: {e}")
    
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
            key_data = encrypted_key[len(ABE_PREFIX):]
            
            # Method 1: Direct DPAPI decryption (works on some configurations)
            try:
                decrypted = win32crypt.CryptUnprotectData(key_data, None, None, None, 0)[1]
                if decrypted and len(decrypted) >= 16:
                    logger.info("ABE key decrypted via direct DPAPI")
                    return decrypted
            except Exception as e:
                logger.debug("Direct DPAPI decryption of ABE key failed: %s", e)
            
            # Method 2: Try Chrome keyring method
            result = _try_decrypt_with_chrome_keyring(encrypted_key)
            if result:
                logger.info("ABE key decrypted via Chrome keyring method")
                return result
            
            # Method 3: Try with CRYPTPROTECT_UI_FORBIDDEN flag
            try:
                CRYPTPROTECT_UI_FORBIDDEN = 0x01
                decrypted = win32crypt.CryptUnprotectData(
                    key_data, None, None, None, CRYPTPROTECT_UI_FORBIDDEN
                )[1]
                if decrypted and len(decrypted) >= 16:
                    logger.info("ABE key decrypted via DPAPI (UI_FORBIDDEN)")
                    return decrypted
            except Exception:
                pass
            
            # Method 4: Try decrypting the full key with APPB prefix
            # Some Chrome versions may use different formats
            try:
                decrypted = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
                if decrypted and len(decrypted) >= 16:
                    logger.info("ABE key decrypted via full key DPAPI")
                    return decrypted
            except Exception:
                pass
        
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


# CDP-based cookie extraction for Chrome 127+
class CDPCookieExtractor:
    """
    Extract cookies using Chrome DevTools Protocol (CDP).
    
    This is the most reliable method for Chrome 127+ with App-Bound Encryption,
    as Chrome itself handles the decryption and returns plaintext cookies via CDP.
    
    Usage:
        extractor = CDPCookieExtractor()
        cookies = extractor.get_all_cookies()
    """
    
    DEFAULT_CDP_PORT = 9222
    CONNECT_TIMEOUT = 10
    
    def __init__(
        self, 
        chrome_path: Optional[Path] = None,
        user_data_dir: Optional[Path] = None,
        cdp_port: int = DEFAULT_CDP_PORT,
    ):
        self._chrome_path = chrome_path or _get_chrome_exe_path()
        self._user_data_dir = user_data_dir
        self._cdp_port = cdp_port
        self._chrome_process: Optional[subprocess.Popen] = None
        self._ws_url: Optional[str] = None
    
    def _find_free_port(self) -> int:
        """Find a free port for CDP."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]
    
    def _get_user_data_dir(self) -> Optional[Path]:
        """Get Chrome's default user data directory."""
        if self._user_data_dir:
            return self._user_data_dir
        
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            chrome_data = Path(local_app_data) / "Google" / "Chrome" / "User Data"
            if chrome_data.exists():
                return chrome_data
        return None
    
    def _start_chrome_with_cdp(self) -> bool:
        """Start Chrome with remote debugging enabled."""
        if not self._chrome_path or not self._chrome_path.exists():
            logger.error("Chrome executable not found")
            return False
        
        user_data_dir = self._get_user_data_dir()
        if not user_data_dir:
            logger.error("Chrome user data directory not found")
            return False
        
        # Find a free port to avoid conflicts
        self._cdp_port = self._find_free_port()
        
        args = [
            str(self._chrome_path),
            f"--remote-debugging-port={self._cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--mute-audio",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        
        try:
            # Start Chrome process
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            self._chrome_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
            )
            
            # Wait for Chrome to start and expose CDP
            import time
            for _ in range(self.CONNECT_TIMEOUT * 10):
                if self._get_ws_endpoint():
                    logger.info(f"Chrome CDP started on port {self._cdp_port}")
                    return True
                time.sleep(0.1)
            
            logger.error("Chrome CDP did not start in time")
            self._cleanup()
            return False
            
        except Exception as e:
            logger.error(f"Failed to start Chrome: {e}")
            self._cleanup()
            return False
    
    def _get_ws_endpoint(self) -> Optional[str]:
        """Get the WebSocket endpoint from CDP."""
        import urllib.request
        import urllib.error
        
        try:
            url = f"http://127.0.0.1:{self._cdp_port}/json/version"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode())
                self._ws_url = data.get("webSocketDebuggerUrl")
                return self._ws_url
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            return None
    
    def _send_cdp_command(self, ws, method: str, params: dict = None) -> dict:
        """Send a CDP command and get the response."""
        import random
        msg_id = random.randint(1, 1000000)
        message = {"id": msg_id, "method": method}
        if params:
            message["params"] = params
        
        ws.send(json.dumps(message))
        
        while True:
            response = json.loads(ws.recv())
            if response.get("id") == msg_id:
                return response
    
    def get_all_cookies(self) -> list[dict]:
        """
        Get all cookies from Chrome using CDP.
        
        Returns a list of cookie dictionaries with decrypted values.
        """
        cookies = []
        
        # Try to connect to existing Chrome instance first
        if not self._get_ws_endpoint():
            # Start Chrome if no existing instance
            if not self._start_chrome_with_cdp():
                return cookies
        
        try:
            import websocket
        except ImportError:
            logger.error("websocket-client not installed. Install with: pip install websocket-client")
            # Try to use websockets instead (async)
            return self._get_cookies_async()
        
        try:
            ws = websocket.create_connection(
                self._ws_url, 
                timeout=self.CONNECT_TIMEOUT
            )
            
            # Get all cookies via CDP
            response = self._send_cdp_command(ws, "Network.getAllCookies")
            
            if "result" in response and "cookies" in response["result"]:
                for cookie in response["result"]["cookies"]:
                    cookies.append({
                        "domain": cookie.get("domain", ""),
                        "name": cookie.get("name", ""),
                        "value": cookie.get("value", ""),
                        "path": cookie.get("path", "/"),
                        "expires": int(cookie.get("expires", 0)),
                        "secure": cookie.get("secure", False),
                        "httponly": cookie.get("httpOnly", False),
                        "samesite": cookie.get("sameSite", ""),
                    })
            
            ws.close()
            
        except Exception as e:
            logger.error(f"CDP cookie extraction failed: {e}")
        
        return cookies
    
    def _get_cookies_async(self) -> list[dict]:
        """Async fallback using websockets library."""
        import asyncio
        
        async def _extract():
            cookies = []
            try:
                import websockets
                
                if not self._ws_url:
                    return cookies
                
                async with websockets.connect(self._ws_url) as ws:
                    import random
                    msg_id = random.randint(1, 1000000)
                    await ws.send(json.dumps({
                        "id": msg_id, 
                        "method": "Network.getAllCookies"
                    }))
                    
                    while True:
                        response = json.loads(await ws.recv())
                        if response.get("id") == msg_id:
                            if "result" in response and "cookies" in response["result"]:
                                for cookie in response["result"]["cookies"]:
                                    cookies.append({
                                        "domain": cookie.get("domain", ""),
                                        "name": cookie.get("name", ""),
                                        "value": cookie.get("value", ""),
                                        "path": cookie.get("path", "/"),
                                        "expires": int(cookie.get("expires", 0)),
                                        "secure": cookie.get("secure", False),
                                        "httponly": cookie.get("httpOnly", False),
                                        "samesite": cookie.get("sameSite", ""),
                                    })
                            break
                            
            except Exception as e:
                logger.error(f"Async CDP extraction failed: {e}")
            
            return cookies
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_extract())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to run async CDP extraction: {e}")
            return []
    
    def _cleanup(self) -> None:
        """Clean up Chrome process."""
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()


def get_cookies_via_cdp(
    chrome_path: Optional[Path] = None,
    user_data_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Get decrypted cookies using Chrome DevTools Protocol.
    
    This is the recommended method for Chrome 127+ with ABE.
    
    Args:
        chrome_path: Path to Chrome executable (auto-detected if None)
        user_data_dir: Chrome user data directory (auto-detected if None)
        
    Returns:
        List of cookie dictionaries with decrypted values
    """
    with CDPCookieExtractor(chrome_path, user_data_dir) as extractor:
        return extractor.get_all_cookies()


def try_cdp_cookie_extraction(browser_name: str = "chrome") -> tuple[bool, list[dict]]:
    """
    Attempt to extract cookies using CDP.
    
    Returns:
        Tuple of (success, cookies)
    """
    try:
        chrome_path = _get_chrome_exe_path()
        if not chrome_path:
            return False, []
        
        extractor = CDPCookieExtractor(chrome_path)
        cookies = extractor.get_all_cookies()
        extractor._cleanup()
        
        if cookies:
            logger.info(f"CDP extraction successful: {len(cookies)} cookies")
            return True, cookies
        
        return False, []
        
    except Exception as e:
        logger.debug(f"CDP extraction failed: {e}")
        return False, []


# Alternative approach using Chrome's Remote Debugging Protocol (legacy wrapper)
def decrypt_via_chrome_devtools(
    local_state_path: Path,
    encrypted_values: list[bytes],
) -> list[Optional[str]]:
    """
    Decrypt values using Chrome's DevTools Protocol.
    
    NOTE: This is a legacy wrapper. For Chrome 127+, use CDPCookieExtractor directly
    to get already-decrypted cookies instead of trying to decrypt raw values.
    
    This method:
    1. Launches Chrome with remote debugging
    2. Connects to DevTools
    3. Uses internal Chrome APIs to decrypt
    4. Returns decrypted values
    """
    # CDP returns already-decrypted cookies, so we can't use it to decrypt
    # raw encrypted values. The correct approach is to use CDPCookieExtractor
    # to get all cookies directly.
    logger.warning(
        "decrypt_via_chrome_devtools is deprecated for ABE. "
        "Use CDPCookieExtractor.get_all_cookies() instead."
    )
    return [None] * len(encrypted_values)


def check_abe_support() -> dict[str, Any]:
    """
    Check system support for App-Bound Encryption decryption.
    
    Returns a dictionary with:
    - windows: Whether running on Windows
    - chrome_installed: Whether Chrome is found
    - chrome_path: Path to Chrome executable
    - elevation_service: Whether elevation service exists
    - elevation_service_path: Path to elevation_service.exe if found
    - elevation_service_running: Whether elevation service is running
    - ielevator_available: Whether IElevator COM is accessible and working
    - dpapi_available: Whether DPAPI is available
    - cdp_available: Whether CDP extraction can be used (recommended for Chrome 127+)
    - recommended_method: The recommended decryption method
    """
    result = {
        "windows": os.name == "nt",
        "chrome_installed": False,
        "chrome_path": None,
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
    
    # Check elevation service file exists
    if chrome_path:
        elevation_service = _get_elevation_service_path()
        result["elevation_service"] = elevation_service is not None
        if elevation_service:
            result["elevation_service_path"] = str(elevation_service)
    
    # Check if elevation service is running
    result["elevation_service_running"] = _is_elevation_service_running()
    
    # If service exists but not running, try to start it
    if result["elevation_service"] and not result["elevation_service_running"]:
        if _start_elevation_service():
            result["elevation_service_running"] = True
    
    # Check DPAPI availability
    try:
        import win32crypt  # type: ignore
        result["dpapi_available"] = True
    except ImportError:
        pass
    
    # Check IElevator COM - actually test if it works
    try:
        import comtypes.client  # type: ignore
        from comtypes import GUID
        
        # Try to create the COM object
        CLSID_Elevator = GUID("{708860E0-F641-4611-8895-7D867DD3675B}")
        try:
            comtypes.client.CoInitialize()
            obj = comtypes.client.CreateObject(CLSID_Elevator)
            result["ielevator_available"] = obj is not None
        except Exception as e:
            logger.debug(f"IElevator COM test failed: {e}")
            # comtypes is installed but COM object not accessible
            result["ielevator_available"] = False
        finally:
            try:
                comtypes.client.CoUninitialize()
            except:
                pass
    except ImportError:
        pass
    
    # Check CDP availability (preferred method for Chrome 127+)
    if result["chrome_installed"]:
        # CDP is available if Chrome is installed and we can use websockets
        try:
            # Check for websocket library
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
    
    # Determine recommended method
    # Priority: CDP > IElevator > DPAPI
    if result["cdp_available"]:
        result["recommended_method"] = "cdp"
    elif result["ielevator_available"]:
        result["recommended_method"] = "ielevator"
    elif result["dpapi_available"]:
        result["recommended_method"] = "dpapi"
    else:
        result["recommended_method"] = "none"
    
    return result


def get_abe_decryption_status_message() -> str:
    """
    Get a human-readable status message about ABE decryption capabilities.
    """
    support = check_abe_support()
    
    if not support["windows"]:
        return "ABE decryption is only supported on Windows."
    
    if not support["chrome_installed"]:
        return "Chrome is not installed. ABE decryption requires Chrome."
    
    messages = []
    
    if support["cdp_available"]:
        messages.append("✓ CDP extraction available (recommended for Chrome 127+)")
    else:
        messages.append("✗ CDP extraction not available (install websocket-client)")
    
    if support["ielevator_available"]:
        messages.append("✓ IElevator COM interface available")
    else:
        messages.append("✗ IElevator COM not accessible (requires special registration)")
    
    if support["dpapi_available"]:
        messages.append("✓ DPAPI available (limited for ABE)")
    else:
        messages.append("✗ DPAPI not available")
    
    messages.append(f"\nRecommended method: {support['recommended_method'].upper()}")
    
    return "\n".join(messages)
