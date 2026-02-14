"""
ABE Native Module - Python wrapper with fallback support.

This module provides a unified interface for ABE decryption that:
1. Uses native C++ implementation when available (Windows)
2. Falls back to pure Python implementation otherwise
"""

from __future__ import annotations

import logging
import sys
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import native module
_native_available = False
_native_module = None

if sys.platform == "win32":
    try:
        from . import abe_native as _native_module
        _native_available = _native_module.is_windows()
        if _native_available:
            logger.debug("ABE native module loaded successfully")
    except ImportError as e:
        logger.debug(f"ABE native module not available: {e}")
        _native_available = False


def is_native_available() -> bool:
    """Check if native ABE module is available."""
    return _native_available


def get_native_module():
    """Get the native module if available."""
    if not _native_available:
        raise RuntimeError("ABE native module not available")
    return _native_module


# Browser type constants
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


def is_abe_encrypted_key(data: bytes) -> bool:
    """Check if data has APPB prefix (App-Bound Encryption key)."""
    if _native_available:
        return _native_module.is_abe_encrypted_key(data)
    return data.startswith(b"APPB")


def is_abe_encrypted_value(data: bytes) -> bool:
    """Check if data has v20 prefix (ABE encrypted value)."""
    if _native_available:
        return _native_module.is_abe_encrypted_value(data)
    return data.startswith(b"v20")


def decrypt_aes_gcm(key: bytes, encrypted_data: bytes) -> Optional[bytes]:
    """
    Decrypt v20 (ABE) encrypted data using AES-GCM.
    
    Args:
        key: 32-byte AES key
        encrypted_data: Data with v20 prefix + IV + ciphertext + tag
        
    Returns:
        Decrypted bytes or None on failure
    """
    if _native_available:
        return _native_module.decrypt_aes_gcm(key, encrypted_data)
    
    # Fallback to Python implementation
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        if not encrypted_data.startswith(b"v20"):
            return None
        
        nonce = encrypted_data[3:15]  # 12 bytes after "v20"
        ciphertext = encrypted_data[15:]
        
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        logger.debug(f"Python AES-GCM decryption failed: {e}")
        return None


def decrypt_aes_gcm_raw(key: bytes, iv: bytes, ciphertext: bytes, tag: bytes) -> Optional[bytes]:
    """
    Decrypt raw AES-GCM data.
    
    Args:
        key: 32-byte AES key
        iv: 12-byte initialization vector
        ciphertext: Encrypted data
        tag: 16-byte authentication tag
        
    Returns:
        Decrypted bytes or None on failure
    """
    if _native_available:
        return _native_module.decrypt_aes_gcm_raw(key, iv, ciphertext, tag)
    
    # Fallback to Python implementation
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(key)
        # AESGCM expects ciphertext + tag concatenated
        return aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception as e:
        logger.debug(f"Python AES-GCM raw decryption failed: {e}")
        return None


class Elevator:
    """
    IElevator COM interface wrapper for ABE key decryption.
    
    Supports Chrome, Edge, Brave, and Avast elevation services.
    Falls back to pure Python COM implementation if native not available.
    """
    
    def __init__(self):
        self._native_elevator = None
        if _native_available:
            try:
                self._native_elevator = _native_module.Elevator()
            except Exception as e:
                logger.warning(f"Failed to create native Elevator: {e}")
    
    def decrypt_key(self, encrypted_key: bytes, browser_type: str) -> Dict[str, Any]:
        """
        Decrypt ABE key using specified browser's elevation service.
        
        Args:
            encrypted_key: APPB-prefixed encrypted key from Local State
            browser_type: Browser type string (BrowserType constant)
            
        Returns:
            Dict with 'success', 'data' (bytes), and 'error' (string)
        """
        if self._native_elevator:
            return self._native_elevator.decrypt_key(encrypted_key, browser_type)
        
        # Fallback to Python COM implementation
        return self._python_decrypt_key(encrypted_key, browser_type)
    
    def decrypt_key_auto(self, encrypted_key: bytes) -> Dict[str, Any]:
        """
        Automatically try all available elevation services to decrypt key.
        
        Args:
            encrypted_key: APPB-prefixed encrypted key from Local State
            
        Returns:
            Dict with 'success', 'data' (bytes), and 'error' (string)
        """
        if self._native_elevator:
            return self._native_elevator.decrypt_key_auto(encrypted_key)
        
        # Fallback: try multiple browsers
        browsers = [
            BrowserType.CHROME,
            BrowserType.EDGE,
            BrowserType.BRAVE,
            BrowserType.CHROME_BETA,
            BrowserType.CHROME_DEV,
            BrowserType.AVAST,
        ]
        
        for browser in browsers:
            result = self._python_decrypt_key(encrypted_key, browser)
            if result.get("success"):
                return result
        
        return {
            "success": False,
            "data": None,
            "error": "All browser elevation services failed",
        }
    
    def _python_decrypt_key(self, encrypted_key: bytes, browser_type: str) -> Dict[str, Any]:
        """Python COM fallback for key decryption."""
        if sys.platform != "win32":
            return {
                "success": False,
                "data": None,
                "error": "ABE decryption requires Windows",
            }
        
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
            
            clsid_str = clsids.get(browser_type)
            if not clsid_str:
                return {
                    "success": False,
                    "data": None,
                    "error": f"Unknown browser type: {browser_type}",
                }
            
            comtypes.client.CoInitialize()
            try:
                clsid = GUID(clsid_str)
                obj = comtypes.client.CreateObject(clsid)
                
                # Call DecryptData
                from ctypes import c_char_p, pointer, c_ulong
                
                result_ptr = c_char_p()
                result_len = c_ulong()
                com_err = c_ulong()
                
                hr = obj.DecryptData(
                    encrypted_key,
                    len(encrypted_key),
                    pointer(result_ptr),
                    pointer(result_len),
                    pointer(com_err)
                )
                
                if hr == 0 and result_ptr.value:
                    return {
                        "success": True,
                        "data": result_ptr.value[:result_len.value],
                        "error": "",
                    }
                else:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"COM DecryptData failed: 0x{hr:08X}",
                    }
            finally:
                comtypes.client.CoUninitialize()
                
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e),
            }


# Export public API
__all__ = [
    "is_native_available",
    "get_native_module",
    "is_abe_encrypted_key",
    "is_abe_encrypted_value",
    "decrypt_aes_gcm",
    "decrypt_aes_gcm_raw",
    "Elevator",
    "BrowserType",
]
