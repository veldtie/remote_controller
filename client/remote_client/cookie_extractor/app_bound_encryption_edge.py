"""
App-Bound Encryption (ABE) module for Microsoft Edge browser cookie decryption.

Microsoft Edge is based on Chromium and uses the same App-Bound Encryption mechanism
as Chrome 127+. This module provides Edge-specific methods using the unified ABE
native module.

Key differences from Chrome:
1. Edge stores data in %LOCALAPPDATA%/Microsoft/Edge/User Data/
2. Edge has its own elevation service with Microsoft-specific CLSIDs
3. Edge uses different service names (MicrosoftEdgeElevationService)
4. Edge has additional interface methods (IElevator2 with RunIsolatedChrome)

References:
- Chrome ABE: https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html
- xaitax's ABE research: https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
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


class EdgeAppBoundDecryptionError(CookieExportError):
    """Raised when Edge App-Bound decryption fails."""

    def __init__(self, message: str) -> None:
        super().__init__("edge_abe_decryption_failed", message)


def _get_edge_exe_path() -> Optional[Path]:
    """Find Microsoft Edge executable path."""
    if os.name != "nt":
        return None
        
    possible_paths = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Try registry
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
    if os.name != "nt":
        return None
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
        result = subprocess.run(
            ["sc", "query", "MicrosoftEdgeElevationService"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "RUNNING" in result.stdout
    except Exception:
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
        return False


def load_edge_abe_key_from_local_state(
    local_state_path: Optional[Path] = None
) -> Optional[bytes]:
    """
    Load and decrypt Edge's ABE key from Local State.
    
    Uses the unified ABE native module for decryption.
    """
    if local_state_path is None:
        local_state_path = _get_edge_local_state_path()
    
    if not local_state_path or not local_state_path.exists():
        logger.warning("Edge Local State file not found")
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            logger.warning("No encrypted_key in Edge Local State")
            return None
        
        encrypted_key = base64.b64decode(encrypted_key_b64)
        
        # Remove DPAPI prefix if present
        if encrypted_key.startswith(DPAPI_PREFIX):
            encrypted_key = encrypted_key[len(DPAPI_PREFIX):]
        
        if is_abe_encrypted_key(encrypted_key):
            # Use Edge-specific browser type
            return decrypt_abe_key(encrypted_key, BrowserType.EDGE, auto_detect=True)
        else:
            # Not ABE, try DPAPI
            return _dpapi_decrypt(encrypted_key)
            
    except Exception as e:
        logger.error(f"Failed to load Edge ABE key: {e}")
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


def decrypt_edge_v20_value(encrypted_value: bytes, abe_key: bytes) -> str:
    """Decrypt a v20 (ABE) encrypted Edge cookie value."""
    result = decrypt_abe_value(encrypted_value, abe_key, strip_header=True)
    if result is None:
        raise EdgeAppBoundDecryptionError("Decryption failed")
    return result


class EdgeAppBoundDecryptor(AppBoundDecryptor):
    """
    High-level interface for Edge App-Bound Encryption decryption.
    
    Extends the base AppBoundDecryptor with Edge-specific functionality.
    """
    
    def __init__(self, local_state_path: Optional[Path] = None):
        """
        Initialize Edge ABE decryptor.
        
        Args:
            local_state_path: Path to Local State file (auto-detected if None)
        """
        if local_state_path is None:
            local_state_path = _get_edge_local_state_path()
        super().__init__(local_state_path, BrowserType.EDGE)
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of ABE key using Edge-specific loading."""
        if self._initialized:
            return
        
        self._initialized = True
        self._abe_key = load_edge_abe_key_from_local_state(self._local_state_path)
        self._available = self._abe_key is not None
        
        if self._available:
            logger.info("Edge ABE decryptor initialized successfully")
        else:
            logger.warning("Edge ABE decryptor initialization failed")


def get_edge_cookies_via_cdp() -> List[Dict[str, Any]]:
    """
    Get decrypted Edge cookies using Chrome DevTools Protocol.
    
    Returns:
        List of cookie dictionaries
    """
    edge_path = _get_edge_exe_path()
    if not edge_path:
        logger.warning("Edge executable not found for CDP extraction")
        return []
    
    user_data_dir = _get_edge_user_data_dir()
    
    try:
        with CDPCookieExtractor(edge_path, user_data_dir) as extractor:
            return extractor.get_all_cookies()
    except Exception as e:
        logger.error(f"Edge CDP extraction failed: {e}")
        return []


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


def check_edge_abe_support() -> Dict[str, Any]:
    """Check system support for Edge App-Bound Encryption decryption."""
    from .app_bound_encryption import check_abe_support
    
    # Get base ABE support info
    result = check_abe_support()
    
    # Add Edge-specific info
    result["edge_installed"] = False
    result["edge_path"] = None
    result["edge_user_data_dir"] = None
    result["edge_elevation_service"] = False
    result["edge_elevation_service_path"] = None
    result["edge_elevation_service_running"] = False
    result["edge_version"] = None
    
    edge_path = _get_edge_exe_path()
    result["edge_installed"] = edge_path is not None
    if edge_path:
        result["edge_path"] = str(edge_path)
    
    user_data_dir = _get_edge_user_data_dir()
    if user_data_dir:
        result["edge_user_data_dir"] = str(user_data_dir)
    
    if edge_path:
        elevation_service = _get_edge_elevation_service_path()
        result["edge_elevation_service"] = elevation_service is not None
        if elevation_service:
            result["edge_elevation_service_path"] = str(elevation_service)
    
    result["edge_elevation_service_running"] = _is_edge_elevation_service_running()
    result["edge_version"] = _get_edge_version()
    
    return result


# Export public API
__all__ = [
    # Classes
    "EdgeAppBoundDecryptionError",
    "EdgeAppBoundDecryptor",
    # Functions
    "load_edge_abe_key_from_local_state",
    "decrypt_edge_v20_value",
    "get_edge_cookies_via_cdp",
    "check_edge_abe_support",
    # Re-exports from main module
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "BrowserType",
]
