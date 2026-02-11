from __future__ import annotations

import base64
import json
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .browsers import resolve_path
from .errors import CookieExportError
from .decrypt import decrypt_chrome_value, get_dpapi, load_local_state_key, _get_abe_decryptor

logger = logging.getLogger(__name__)


def _detect_abe_version(local_state_path: Optional[Path]) -> bool:
    """
    Detect if Chrome uses App-Bound Encryption (v20 cookies).
    Returns True if ABE is detected.
    """
    if not local_state_path or not local_state_path.exists():
        return False
    
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key", "")
        encrypted_key = base64.b64decode(encrypted_key_b64)
        return encrypted_key.startswith(b"APPB")
    except Exception:
        return False


def copy_db(db_path: Path) -> Path | None:
    try:
        handle = tempfile.NamedTemporaryFile(prefix="rc_cookies_", suffix=db_path.suffix, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception:
        return None


def _check_abe_support(local_state_path: Optional[Path], browser_name: str = "chrome") -> Dict:
    """Check App-Bound Encryption support status."""
    result = {
        "detected": False,
        "available": False,
        "method": None,
    }
    
    if not local_state_path:
        return result
    
    import json
    import base64
    
    # Helper to check if ABE key exists
    def check_abe_key():
        try:
            raw = local_state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            encrypted_key_b64 = data["os_crypt"]["encrypted_key"]
            encrypted_key = base64.b64decode(encrypted_key_b64)
            return encrypted_key.startswith(b"APPB")
        except Exception:
            return False
    
    result["detected"] = check_abe_key()
    
    # Use browser-specific ABE module
    if browser_name == "opera":
        try:
            from .app_bound_encryption_opera import check_opera_abe_support
            support = check_opera_abe_support()
            result.update(support)
        except ImportError:
            pass
    elif browser_name == "edge":
        try:
            from .app_bound_encryption_edge import check_edge_abe_support
            support = check_edge_abe_support()
            result.update(support)
        except ImportError:
            pass
    elif browser_name == "brave":
        try:
            from .app_bound_encryption_brave import check_brave_abe_support
            support = check_brave_abe_support()
            result.update(support)
        except ImportError:
            pass
    elif browser_name == "dolphin_anty":
        try:
            from .app_bound_encryption_dolphin import check_dolphin_abe_support
            support = check_dolphin_abe_support()
            result.update(support)
        except ImportError:
            pass
    else:
        # Default Chrome ABE support check
        try:
            from .app_bound_encryption import check_abe_support
            support = check_abe_support()
            result.update(support)
        except ImportError:
            pass
    
    return result


def _get_browser_exe_path(browser_name: str) -> Optional[Path]:
    """
    Get the executable path for a Chromium-based browser.
    """
    import os
    
    # Browser-specific paths
    browser_paths = {
        "chrome": [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ],
        "edge": [
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ],
        "brave": [
            Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ],
        "opera": [
            Path(os.environ.get("PROGRAMFILES", "")) / "Opera" / "opera.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera" / "opera.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera" / "opera.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera" / "launcher.exe",
            # Opera GX
            Path(os.environ.get("PROGRAMFILES", "")) / "Opera GX" / "opera.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera GX" / "opera.exe",
        ],
        "dolphin_anty": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "DolphinAnty.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Dolphin Anty" / "dolphin-anty.exe",
            Path(os.environ.get("APPDATA", "")) / "Dolphin Anty" / "DolphinAnty.exe",
        ],
        "octo": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Octo Browser" / "OctoBrowser.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Octo Browser" / "Application" / "OctoBrowser.exe",
            Path(os.environ.get("APPDATA", "")) / "Octo Browser" / "OctoBrowser.exe",
        ],
        "adspower": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "AdsPower" / "AdsPower.exe",
            Path(os.environ.get("APPDATA", "")) / "AdsPower" / "AdsPower.exe",
        ],
        "uc_browser": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "UCBrowser" / "Application" / "UCBrowser.exe",
        ],
    }
    
    paths = browser_paths.get(browser_name.lower(), [])
    for path in paths:
        if path.exists():
            return path
    
    return None


def _try_cdp_extraction(browser_name: str, config: Dict) -> tuple[bool, List[Dict]]:
    """
    Try to extract cookies using Chrome DevTools Protocol (CDP).
    
    This is the preferred method for Chromium-based browsers with ABE (Chrome 127+).
    Works for: Chrome, Edge, Brave, Opera, Dolphin Anty, and other Chromium browsers.
    
    Returns (success, cookies).
    """
    # CDP works for all Chromium-based browsers
    chromium_browsers = {
        "chrome", "google chrome", "edge", "microsoft edge", "brave", 
        "opera", "dolphin_anty", "octo", "adspower", "uc_browser",
        "huawei_browser", "samsung_internet", "linken_sphere_2"
    }
    
    if browser_name.lower() not in chromium_browsers:
        return False, []
    
    try:
        from .app_bound_encryption import CDPCookieExtractor
        
        # Get browser executable path
        browser_exe = _get_browser_exe_path(browser_name)
        if not browser_exe:
            # For less common browsers, try to use Chrome as CDP host
            # since CDP protocol is standard across Chromium
            from .app_bound_encryption import _get_chrome_exe_path
            browser_exe = _get_chrome_exe_path()
            if not browser_exe:
                logger.debug(f"No suitable browser executable found for CDP extraction ({browser_name})")
                return False, []
            logger.debug(f"Using Chrome for CDP extraction of {browser_name} cookies")
        
        # Get user data directory from config
        import os
        user_data_dir = None
        local_state_path = resolve_path(config.get("local_state")) if config.get("local_state") else None
        if local_state_path and local_state_path.exists():
            # User Data is parent of Local State
            user_data_dir = local_state_path.parent
        
        logger.info(f"Attempting CDP extraction for {browser_name} (ABE/v20 detected)...")
        
        extractor = CDPCookieExtractor(browser_exe, user_data_dir)
        try:
            cdp_cookies = extractor.get_all_cookies()
        finally:
            extractor._cleanup()
        
        if cdp_cookies:
            # Convert CDP format to our format
            cookies = []
            for c in cdp_cookies:
                cookies.append({
                    "browser": browser_name,
                    "domain": c.get("domain", ""),
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                    "path": c.get("path", "/"),
                    "expires": c.get("expires", 0),
                    "secure": c.get("secure", False),
                    "httponly": c.get("httponly", False),
                })
            
            logger.info(f"CDP extraction successful for {browser_name}: {len(cookies)} cookies extracted")
            return True, cookies
        
        logger.debug(f"CDP extraction returned no cookies for {browser_name}")
        return False, []
        
    except Exception as e:
        logger.debug(f"CDP extraction failed for {browser_name}: {e}")
        return False, []


def extract_chrome_like(browser_name: str, config: Dict) -> List[Dict]:
    """
    Extract cookies from Chrome-like browsers.
    
    Supports:
    - Standard DPAPI encryption (Chrome < 127)
    - App-Bound Encryption (Chrome 127+, Opera) via CDP
    - Multiple encryption versions (v10, v11, v12, v20)
    
    For Chrome 127+ with ABE, CDP is used as the primary method because:
    1. IElevator COM is not accessible without special registration
    2. DPAPI alone cannot decrypt ABE-protected keys
    3. CDP gets already-decrypted cookies directly from Chrome
    """
    dpapi = get_dpapi()
    local_state_path = resolve_path(config.get("local_state")) if config.get("local_state") else None
    
    # Detect if ABE is in use (Chrome 127+)
    abe_detected = _detect_abe_version(local_state_path)
    
    # Check ABE support and log status
    abe_status = _check_abe_support(local_state_path, browser_name)
    if abe_detected:
        logger.info(
            "App-Bound Encryption (v20) detected for %s. Using CDP as primary method.",
            browser_name
        )
        
        # Try CDP first for ABE-protected browsers (Chrome 127+)
        cdp_success, cdp_cookies = _try_cdp_extraction(browser_name, config)
        if cdp_success and cdp_cookies:
            return cdp_cookies
        
        logger.warning(
            "CDP extraction failed for %s. Falling back to traditional methods "
            "(may result in [abe_decrypt_failed] for v20 cookies).",
            browser_name
        )
    
    # Load encryption key (handles both DPAPI and ABE)
    local_state_key = load_local_state_key(local_state_path, dpapi, browser_name)
    
    # Get ABE decryptor for v20 values (browser-specific)
    abe_decryptor = _get_abe_decryptor(local_state_path, browser_name)
    
    cookies: List[Dict] = []
    found_any = False
    decrypt_stats = {"success": 0, "failed": 0, "abe_failed": 0, "v20_count": 0}

    for base_path in config.get("cookie_paths", []):
        resolved = resolve_path(base_path)
        if not resolved or not resolved.exists():
            continue
        found_any = True
        temp_db = copy_db(resolved)
        if not temp_db:
            continue
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly
                FROM cookies
                """
            )
            for row in cursor.fetchall():
                value = row[2] or ""
                encrypted_value = row[3]
                if encrypted_value:
                    # Track v20 (ABE) cookies
                    if isinstance(encrypted_value, (bytes, memoryview)):
                        ev_bytes = bytes(encrypted_value) if isinstance(encrypted_value, memoryview) else encrypted_value
                        if ev_bytes.startswith(b"v20"):
                            decrypt_stats["v20_count"] += 1
                    
                    decrypted = decrypt_chrome_value(
                        encrypted_value, 
                        dpapi, 
                        local_state_key,
                        abe_decryptor
                    )
                    if decrypted.startswith("[") and decrypted.endswith("_failed]"):
                        decrypt_stats["failed"] += 1
                        if "abe" in decrypted:
                            decrypt_stats["abe_failed"] += 1
                    else:
                        decrypt_stats["success"] += 1
                    value = decrypted
                cookies.append(
                    {
                        "browser": browser_name,
                        "domain": row[0],
                        "name": row[1],
                        "value": value,
                        "path": row[4],
                        "expires": row[5],
                        "secure": bool(row[6]),
                        "httponly": bool(row[7]),
                    }
                )
            conn.close()
        except Exception as e:
            logger.debug("Error reading cookies database for %s: %s", browser_name, e)
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass
    
    if not found_any:
        raise CookieExportError(
            "cookies_not_found",
            f"Cookies database not found for {browser_name}.",
        )
    
    # Log decryption statistics with v20 info
    total = decrypt_stats["success"] + decrypt_stats["failed"]
    if total > 0:
        if decrypt_stats["v20_count"] > 0:
            logger.info(
                "%s cookie decryption: %d/%d successful, %d ABE (v20) failures out of %d v20 cookies. "
                "Consider using CDP method for Chrome 127+.",
                browser_name,
                decrypt_stats["success"],
                total,
                decrypt_stats["abe_failed"],
                decrypt_stats["v20_count"]
            )
        else:
            logger.info(
                "%s cookie decryption: %d/%d successful",
                browser_name,
                decrypt_stats["success"],
                total
            )
    
    return cookies
