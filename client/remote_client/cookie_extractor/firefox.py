"""
Firefox and Firefox forks cookie extraction module.

Firefox uses a different encryption system than Chromium browsers:
- Cookies are stored in plain text in cookies.sqlite (moz_cookies table)
- Passwords are encrypted using NSS (Network Security Services) with key4.db
- Firefox does NOT use App-Bound Encryption (ABE)

Supported browsers:
- Firefox (standard)
- Firefox Developer Edition
- Firefox Nightly
- Waterfox
- LibreWolf
- Pale Moon
- Tor Browser
- Floorp
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .browsers import resolve_path
from .errors import CookieExportError
from .extractors import copy_db

logger = logging.getLogger(__name__)

# Firefox-based browser configurations
FIREFOX_BROWSERS = {
    "firefox": {
        "name": "Firefox",
        "profiles_paths": [
            Path("APPDATA") / "Mozilla" / "Firefox" / "Profiles",
        ],
    },
    "firefox_dev": {
        "name": "Firefox Developer Edition",
        "profiles_paths": [
            Path("APPDATA") / "Mozilla" / "Firefox Developer Edition" / "Profiles",
        ],
    },
    "firefox_nightly": {
        "name": "Firefox Nightly",
        "profiles_paths": [
            Path("APPDATA") / "Mozilla" / "Firefox Nightly" / "Profiles",
        ],
    },
    "waterfox": {
        "name": "Waterfox",
        "profiles_paths": [
            Path("APPDATA") / "Waterfox" / "Profiles",
        ],
    },
    "librewolf": {
        "name": "LibreWolf",
        "profiles_paths": [
            Path("APPDATA") / "LibreWolf" / "Profiles",
            Path("APPDATA") / "librewolf" / "Profiles",
        ],
    },
    "pale_moon": {
        "name": "Pale Moon",
        "profiles_paths": [
            Path("APPDATA") / "Moonchild Productions" / "Pale Moon" / "Profiles",
        ],
    },
    "tor_browser": {
        "name": "Tor Browser",
        "profiles_paths": [
            Path("APPDATA") / "Tor Browser" / "Browser" / "TorBrowser" / "Data" / "Browser" / "profile.default",
            # Tor Browser stores profile in Desktop or Downloads typically
        ],
    },
    "floorp": {
        "name": "Floorp",
        "profiles_paths": [
            Path("APPDATA") / "Floorp" / "Profiles",
        ],
    },
}


def _get_firefox_exe_path(browser_key: str = "firefox") -> Optional[Path]:
    """Find Firefox executable path."""
    if os.name != "nt":
        return None
    
    exe_names = {
        "firefox": ["firefox.exe"],
        "firefox_dev": ["firefox.exe"],
        "firefox_nightly": ["firefox.exe"],
        "waterfox": ["waterfox.exe"],
        "librewolf": ["librewolf.exe"],
        "pale_moon": ["palemoon.exe"],
        "tor_browser": ["firefox.exe", "Browser/firefox.exe"],
        "floorp": ["floorp.exe"],
    }
    
    search_dirs = [
        Path(os.environ.get("PROGRAMFILES", "")),
        Path(os.environ.get("PROGRAMFILES(X86)", "")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    ]
    
    browser_dirs = {
        "firefox": ["Mozilla Firefox"],
        "firefox_dev": ["Firefox Developer Edition"],
        "firefox_nightly": ["Firefox Nightly"],
        "waterfox": ["Waterfox"],
        "librewolf": ["LibreWolf"],
        "pale_moon": ["Pale Moon"],
        "tor_browser": ["Tor Browser"],
        "floorp": ["Floorp"],
    }
    
    for search_dir in search_dirs:
        for browser_dir in browser_dirs.get(browser_key, []):
            for exe_name in exe_names.get(browser_key, ["firefox.exe"]):
                exe_path = search_dir / browser_dir / exe_name
                if exe_path.exists():
                    return exe_path
    
    return None


def get_firefox_cookie_paths(browser_key: str = "firefox") -> List[Path]:
    """Get cookie database paths for Firefox or Firefox fork."""
    config = FIREFOX_BROWSERS.get(browser_key, FIREFOX_BROWSERS["firefox"])
    profiles_paths = config.get("profiles_paths", [])
    
    paths: List[Path] = []
    for profiles_path_template in profiles_paths:
        profiles_path = resolve_path(profiles_path_template)
        if not profiles_path or not profiles_path.exists():
            continue
        
        # Handle case where profiles_path is the profile itself (Tor Browser)
        cookie_file = profiles_path / "cookies.sqlite"
        if cookie_file.exists():
            paths.append(cookie_file)
            continue
        
        # Standard case: iterate through profile directories
        try:
            for profile in profiles_path.iterdir():
                if not profile.is_dir():
                    continue
                cookie_file = profile / "cookies.sqlite"
                if cookie_file.exists():
                    paths.append(cookie_file)
        except Exception as e:
            logger.debug(f"Error listing profiles for {browser_key}: {e}")
    
    return paths


def get_all_firefox_cookie_paths() -> Dict[str, List[Path]]:
    """Get cookie paths for all Firefox-based browsers."""
    all_paths: Dict[str, List[Path]] = {}
    for browser_key in FIREFOX_BROWSERS:
        paths = get_firefox_cookie_paths(browser_key)
        if paths:
            all_paths[browser_key] = paths
    return all_paths


def extract_firefox(browser_key: str = "firefox") -> List[Dict]:
    """Extract cookies from Firefox or Firefox fork."""
    config = FIREFOX_BROWSERS.get(browser_key, FIREFOX_BROWSERS["firefox"])
    browser_name = config.get("name", "Firefox")
    
    cookies: List[Dict] = []
    paths = get_firefox_cookie_paths(browser_key)
    if not paths:
        raise CookieExportError(
            "cookies_not_found",
            f"{browser_name} cookies database not found.",
        )
    for db_path in paths:
        temp_db = copy_db(db_path)
        if not temp_db:
            continue
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT host, name, value, path, expiry, isSecure, isHttpOnly
                FROM moz_cookies
                """
            )
            profile_name = db_path.parent.name
            for row in cursor.fetchall():
                cookies.append(
                    {
                        "browser": browser_key,
                        "browser_name": browser_name,
                        "profile": profile_name,
                        "domain": row[0],
                        "name": row[1],
                        "value": row[2],
                        "path": row[3],
                        "expires": row[4],
                        "secure": bool(row[5]),
                        "httponly": bool(row[6]),
                    }
                )
            conn.close()
        except Exception as e:
            logger.debug(f"Error reading cookies from {db_path}: {e}")
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass
    return cookies


def extract_all_firefox_browsers() -> List[Dict]:
    """Extract cookies from all installed Firefox-based browsers."""
    all_cookies: List[Dict] = []
    for browser_key in FIREFOX_BROWSERS:
        try:
            cookies = extract_firefox(browser_key)
            all_cookies.extend(cookies)
        except CookieExportError:
            # Browser not installed, skip
            pass
        except Exception as e:
            logger.debug(f"Error extracting cookies from {browser_key}: {e}")
    return all_cookies


def check_firefox_support(browser_key: str = "firefox") -> Dict[str, Any]:
    """Check Firefox installation and cookie extraction support."""
    config = FIREFOX_BROWSERS.get(browser_key, FIREFOX_BROWSERS["firefox"])
    browser_name = config.get("name", "Firefox")
    
    result = {
        "browser_key": browser_key,
        "browser_name": browser_name,
        "installed": False,
        "exe_path": None,
        "profiles_found": 0,
        "cookie_files_found": 0,
        "total_cookies": 0,
        "uses_abe": False,  # Firefox does NOT use ABE
        "encryption": "none",  # Cookies are not encrypted in Firefox
    }
    
    exe_path = _get_firefox_exe_path(browser_key)
    if exe_path:
        result["installed"] = True
        result["exe_path"] = str(exe_path)
    
    cookie_paths = get_firefox_cookie_paths(browser_key)
    result["cookie_files_found"] = len(cookie_paths)
    
    # Count profiles
    profiles = set()
    for path in cookie_paths:
        profiles.add(path.parent.name)
    result["profiles_found"] = len(profiles)
    
    # Count total cookies
    total = 0
    for db_path in cookie_paths:
        temp_db = copy_db(db_path)
        if temp_db:
            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM moz_cookies")
                total += cursor.fetchone()[0]
                conn.close()
            except Exception:
                pass
            finally:
                try:
                    temp_db.unlink(missing_ok=True)
                except Exception:
                    pass
    result["total_cookies"] = total
    
    return result


def check_all_firefox_support() -> Dict[str, Dict[str, Any]]:
    """Check support for all Firefox-based browsers."""
    results: Dict[str, Dict[str, Any]] = {}
    for browser_key in FIREFOX_BROWSERS:
        results[browser_key] = check_firefox_support(browser_key)
    return results


def get_firefox_version(browser_key: str = "firefox") -> Optional[str]:
    """Get Firefox version from installation."""
    if os.name != "nt":
        return None
    
    exe_path = _get_firefox_exe_path(browser_key)
    if not exe_path:
        return None
    
    # Try to read version from application.ini
    app_ini = exe_path.parent / "application.ini"
    if app_ini.exists():
        try:
            content = app_ini.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("Version="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            pass
    
    # Try registry
    try:
        import winreg
        registry_paths = {
            "firefox": r"SOFTWARE\Mozilla\Mozilla Firefox",
            "waterfox": r"SOFTWARE\Waterfox",
            "librewolf": r"SOFTWARE\LibreWolf",
        }
        reg_path = registry_paths.get(browser_key)
        if reg_path:
            for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(hkey, reg_path) as key:
                        version, _ = winreg.QueryValueEx(key, "CurrentVersion")
                        if version:
                            return version
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    
    return None
