"""
Browser configuration for cookie extraction.

Supports:
- Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi, Yandex, etc.)
- Firefox-based browsers (Firefox, Waterfox, LibreWolf, etc.)
- Anti-detect browsers (Dolphin Anty, Octo, AdsPower, Linken Sphere, etc.)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional


def _chromium_paths(base_path: Path) -> Dict:
    """Generate standard Chromium browser paths."""
    return {
        "type": "chromium",
        "cookie_paths": [
            base_path / "Default" / "Cookies",
            base_path / "Default" / "Network" / "Cookies",
        ],
        "local_state": base_path / "Local State",
        "user_data_dir": base_path,
    }


def _chromium_paths_multi(paths: List[Path]) -> Dict:
    """Generate Chromium paths from multiple possible base paths."""
    cookie_paths = []
    local_states = []
    for base in paths:
        cookie_paths.extend([
            base / "Default" / "Cookies",
            base / "Default" / "Network" / "Cookies",
        ])
        local_states.append(base / "Local State")
    return {
        "type": "chromium",
        "cookie_paths": cookie_paths,
        "local_state": local_states[0] if local_states else None,
        "local_state_paths": local_states,
    }


BROWSER_CONFIG = {
    # ═══════════════════════════════════════════════════════════════════
    # MAJOR BROWSERS
    # ═══════════════════════════════════════════════════════════════════
    
    "chrome": {
        "type": "chromium",
        "name": "Google Chrome",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data" / "Local State",
        "user_data_dir": Path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data",
        "exe_paths": [
            Path("PROGRAMFILES") / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path("PROGRAMFILES(X86)") / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path("LOCALAPPDATA") / "Google" / "Chrome" / "Application" / "chrome.exe",
        ],
    },
    
    "chrome_beta": {
        "type": "chromium",
        "name": "Google Chrome Beta",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Google" / "Chrome Beta" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Google" / "Chrome Beta" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Google" / "Chrome Beta" / "User Data" / "Local State",
    },
    
    "chrome_canary": {
        "type": "chromium",
        "name": "Google Chrome Canary",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Google" / "Chrome SxS" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Google" / "Chrome SxS" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Google" / "Chrome SxS" / "User Data" / "Local State",
    },
    
    "chromium": {
        "type": "chromium",
        "name": "Chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Chromium" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Chromium" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Chromium" / "User Data" / "Local State",
    },
    
    "edge": {
        "type": "chromium",
        "name": "Microsoft Edge",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data" / "Local State",
        "user_data_dir": Path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data",
        "exe_paths": [
            Path("PROGRAMFILES") / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path("PROGRAMFILES(X86)") / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ],
    },
    
    "edge_beta": {
        "type": "chromium",
        "name": "Microsoft Edge Beta",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Microsoft" / "Edge Beta" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Microsoft" / "Edge Beta" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Microsoft" / "Edge Beta" / "User Data" / "Local State",
    },
    
    "edge_dev": {
        "type": "chromium",
        "name": "Microsoft Edge Dev",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Microsoft" / "Edge Dev" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Microsoft" / "Edge Dev" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Microsoft" / "Edge Dev" / "User Data" / "Local State",
    },
    
    "brave": {
        "type": "chromium",
        "name": "Brave Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "BraveSoftware" / "Brave-Browser" / "User Data" / "Local State",
        "user_data_dir": Path("LOCALAPPDATA") / "BraveSoftware" / "Brave-Browser" / "User Data",
        "exe_paths": [
            Path("PROGRAMFILES") / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path("LOCALAPPDATA") / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ],
    },
    
    "opera": {
        "type": "chromium",
        "name": "Opera",
        "cookie_paths": [
            Path("APPDATA") / "Opera Software" / "Opera Stable" / "Cookies",
            Path("APPDATA") / "Opera Software" / "Opera Stable" / "Network" / "Cookies",
        ],
        "local_state": Path("APPDATA") / "Opera Software" / "Opera Stable" / "Local State",
        "user_data_dir": Path("APPDATA") / "Opera Software" / "Opera Stable",
        "exe_paths": [
            Path("LOCALAPPDATA") / "Programs" / "Opera" / "opera.exe",
            Path("PROGRAMFILES") / "Opera" / "opera.exe",
        ],
    },
    
    "opera_gx": {
        "type": "chromium",
        "name": "Opera GX",
        "cookie_paths": [
            Path("APPDATA") / "Opera Software" / "Opera GX Stable" / "Cookies",
            Path("APPDATA") / "Opera Software" / "Opera GX Stable" / "Network" / "Cookies",
        ],
        "local_state": Path("APPDATA") / "Opera Software" / "Opera GX Stable" / "Local State",
        "user_data_dir": Path("APPDATA") / "Opera Software" / "Opera GX Stable",
        "exe_paths": [
            Path("LOCALAPPDATA") / "Programs" / "Opera GX" / "opera.exe",
        ],
    },
    
    "opera_crypto": {
        "type": "chromium",
        "name": "Opera Crypto",
        "cookie_paths": [
            Path("APPDATA") / "Opera Software" / "Opera Crypto Stable" / "Cookies",
            Path("APPDATA") / "Opera Software" / "Opera Crypto Stable" / "Network" / "Cookies",
        ],
        "local_state": Path("APPDATA") / "Opera Software" / "Opera Crypto Stable" / "Local State",
    },
    
    "vivaldi": {
        "type": "chromium",
        "name": "Vivaldi",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Vivaldi" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Vivaldi" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Vivaldi" / "User Data" / "Local State",
        "user_data_dir": Path("LOCALAPPDATA") / "Vivaldi" / "User Data",
    },
    
    "yandex": {
        "type": "chromium",
        "name": "Yandex Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Yandex" / "YandexBrowser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Yandex" / "YandexBrowser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Yandex" / "YandexBrowser" / "User Data" / "Local State",
        "user_data_dir": Path("LOCALAPPDATA") / "Yandex" / "YandexBrowser" / "User Data",
    },
    
    "arc": {
        "type": "chromium",
        "name": "Arc Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Arc" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Arc" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Arc" / "User Data" / "Local State",
    },
    
    # ═══════════════════════════════════════════════════════════════════
    # LESSER-KNOWN CHROMIUM BROWSERS
    # ═══════════════════════════════════════════════════════════════════
    
    "coccoc": {
        "type": "chromium",
        "name": "Coc Coc Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "CocCoc" / "Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "CocCoc" / "Browser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "CocCoc" / "Browser" / "User Data" / "Local State",
    },
    
    "centbrowser": {
        "type": "chromium",
        "name": "CentBrowser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "CentBrowser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "CentBrowser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "CentBrowser" / "User Data" / "Local State",
    },
    
    "iridium": {
        "type": "chromium",
        "name": "Iridium Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Iridium" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Iridium" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Iridium" / "User Data" / "Local State",
    },
    
    "slimjet": {
        "type": "chromium",
        "name": "Slimjet",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Slimjet" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Slimjet" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Slimjet" / "User Data" / "Local State",
    },
    
    "comodo_dragon": {
        "type": "chromium",
        "name": "Comodo Dragon",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Comodo" / "Dragon" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Comodo" / "Dragon" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Comodo" / "Dragon" / "User Data" / "Local State",
    },
    
    "torch": {
        "type": "chromium",
        "name": "Torch Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Torch" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Torch" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Torch" / "User Data" / "Local State",
    },
    
    "7star": {
        "type": "chromium",
        "name": "7Star Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "7Star" / "7Star" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "7Star" / "7Star" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "7Star" / "7Star" / "User Data" / "Local State",
    },
    
    "amigo": {
        "type": "chromium",
        "name": "Amigo Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Amigo" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Amigo" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Amigo" / "User Data" / "Local State",
    },
    
    "sputnik": {
        "type": "chromium",
        "name": "Sputnik Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Sputnik" / "Sputnik" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Sputnik" / "Sputnik" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Sputnik" / "Sputnik" / "User Data" / "Local State",
    },
    
    "epic_privacy": {
        "type": "chromium",
        "name": "Epic Privacy Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Epic Privacy Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Epic Privacy Browser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Epic Privacy Browser" / "User Data" / "Local State",
    },
    
    "uran": {
        "type": "chromium",
        "name": "uCozMedia Uran",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "uCozMedia" / "Uran" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "uCozMedia" / "Uran" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "uCozMedia" / "Uran" / "User Data" / "Local State",
    },
    
    "maxthon": {
        "type": "chromium",
        "name": "Maxthon Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Maxthon" / "Application" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Maxthon" / "Application" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Maxthon" / "Application" / "User Data" / "Local State",
    },
    
    "whale": {
        "type": "chromium",
        "name": "Naver Whale",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Naver" / "Naver Whale" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Naver" / "Naver Whale" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Naver" / "Naver Whale" / "User Data" / "Local State",
    },
    
    "360_browser": {
        "type": "chromium",
        "name": "360 Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "360Chrome" / "Chrome" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "360Chrome" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "360Chrome" / "Chrome" / "User Data" / "Local State",
    },
    
    "qq_browser": {
        "type": "chromium",
        "name": "QQ Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Tencent" / "QQBrowser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Tencent" / "QQBrowser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Tencent" / "QQBrowser" / "User Data" / "Local State",
    },
    
    "sogou_explorer": {
        "type": "chromium",
        "name": "Sogou Explorer",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Sogou" / "SogouExplorer" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Sogou" / "SogouExplorer" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Sogou" / "SogouExplorer" / "User Data" / "Local State",
    },
    
    "uc_browser": {
        "type": "chromium",
        "name": "UC Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "UCBrowser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "UCBrowser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "UCBrowser" / "User Data" / "Local State",
    },
    
    "huawei_browser": {
        "type": "chromium",
        "name": "Huawei Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Huawei" / "Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Huawei" / "Browser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Huawei" / "Browser" / "User Data" / "Local State",
    },
    
    "samsung_internet": {
        "type": "chromium",
        "name": "Samsung Internet",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Samsung" / "Samsung Internet" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Samsung" / "Samsung Internet" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Samsung" / "Samsung Internet" / "User Data" / "Local State",
    },
    
    # ═══════════════════════════════════════════════════════════════════
    # ANTI-DETECT BROWSERS
    # ═══════════════════════════════════════════════════════════════════
    
    "dolphin_anty": {
        "type": "chromium",
        "name": "Dolphin Anty",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Dolphin Anty" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Dolphin Anty" / "User Data" / "Default" / "Network" / "Cookies",
            Path("APPDATA") / "Dolphin Anty" / "User Data" / "Default" / "Cookies",
            Path("APPDATA") / "Dolphin Anty" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Dolphin Anty" / "User Data" / "Local State",
    },
    
    "octo": {
        "type": "chromium",
        "name": "Octo Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Octo Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Octo Browser" / "User Data" / "Default" / "Network" / "Cookies",
            Path("APPDATA") / "Octo Browser" / "User Data" / "Default" / "Cookies",
            Path("APPDATA") / "Octo Browser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Octo Browser" / "User Data" / "Local State",
    },
    
    "adspower": {
        "type": "chromium",
        "name": "AdsPower",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "AdsPower" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "AdsPower" / "User Data" / "Default" / "Network" / "Cookies",
            Path("APPDATA") / "AdsPower" / "User Data" / "Default" / "Cookies",
            Path("APPDATA") / "AdsPower" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "AdsPower" / "User Data" / "Local State",
    },
    
    "linken_sphere_2": {
        "type": "chromium",
        "name": "Linken Sphere 2",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Linken Sphere 2" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Linken Sphere 2" / "User Data" / "Default" / "Network" / "Cookies",
            Path("APPDATA") / "Linken Sphere 2" / "User Data" / "Default" / "Cookies",
            Path("APPDATA") / "Linken Sphere 2" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Linken Sphere 2" / "User Data" / "Local State",
    },
    
    "multilogin": {
        "type": "chromium",
        "name": "Multilogin",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Multilogin" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Multilogin" / "User Data" / "Default" / "Network" / "Cookies",
            Path("APPDATA") / "Multilogin" / "User Data" / "Default" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Multilogin" / "User Data" / "Local State",
    },
    
    "gologin": {
        "type": "chromium",
        "name": "GoLogin",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "GoLogin" / "Browser" / "orbita-browser" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "GoLogin" / "Browser" / "orbita-browser" / "Default" / "Network" / "Cookies",
            Path("APPDATA") / "GoLogin" / "Browser" / "orbita-browser" / "Default" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "GoLogin" / "Browser" / "orbita-browser" / "Local State",
    },
    
    "indigo": {
        "type": "chromium",
        "name": "Indigo Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Indigo" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Indigo" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Indigo" / "User Data" / "Local State",
    },
    
    "ghost_browser": {
        "type": "chromium",
        "name": "Ghost Browser",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "GhostBrowser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "GhostBrowser" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "GhostBrowser" / "User Data" / "Local State",
    },
    
    "vmlogin": {
        "type": "chromium",
        "name": "VMLogin",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "VMLogin" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "VMLogin" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "VMLogin" / "User Data" / "Local State",
    },
    
    "incognition": {
        "type": "chromium",
        "name": "Incogniton",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Incogniton" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Incogniton" / "User Data" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Incogniton" / "User Data" / "Local State",
    },
    
    "kameleo": {
        "type": "chromium",
        "name": "Kameleo",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Kameleo" / "profiles" / "Default" / "Cookies",
            Path("LOCALAPPDATA") / "Kameleo" / "profiles" / "Default" / "Network" / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Kameleo" / "profiles" / "Local State",
    },
    
    # ═══════════════════════════════════════════════════════════════════
    # FIREFOX-BASED BROWSERS
    # ═══════════════════════════════════════════════════════════════════
    
    "firefox": {
        "type": "firefox",
        "name": "Mozilla Firefox",
        "profiles_path": Path("APPDATA") / "Mozilla" / "Firefox" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "firefox_dev": {
        "type": "firefox",
        "name": "Firefox Developer Edition",
        "profiles_path": Path("APPDATA") / "Mozilla" / "Firefox Developer Edition" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "firefox_nightly": {
        "type": "firefox",
        "name": "Firefox Nightly",
        "profiles_path": Path("APPDATA") / "Mozilla" / "Firefox Nightly" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "waterfox": {
        "type": "firefox",
        "name": "Waterfox",
        "profiles_path": Path("APPDATA") / "Waterfox" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "librewolf": {
        "type": "firefox",
        "name": "LibreWolf",
        "profiles_path": Path("APPDATA") / "LibreWolf" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "pale_moon": {
        "type": "firefox",
        "name": "Pale Moon",
        "profiles_path": Path("APPDATA") / "Moonchild Productions" / "Pale Moon" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "basilisk": {
        "type": "firefox",
        "name": "Basilisk",
        "profiles_path": Path("APPDATA") / "Moonchild Productions" / "Basilisk" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "seamonkey": {
        "type": "firefox",
        "name": "SeaMonkey",
        "profiles_path": Path("APPDATA") / "Mozilla" / "SeaMonkey" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
    
    "tor_browser": {
        "type": "firefox",
        "name": "Tor Browser",
        "profiles_path": Path("USERPROFILE") / "Desktop" / "Tor Browser" / "Browser" / "TorBrowser" / "Data" / "Browser" / "profile.default",
        "cookie_file": "cookies.sqlite",
        "is_single_profile": True,
    },
}


def resolve_path(path: Path) -> Path | None:
    """Resolve environment variables in path."""
    env_map = {
        "LOCALAPPDATA": os.getenv("LOCALAPPDATA"),
        "APPDATA": os.getenv("APPDATA"),
        "USERPROFILE": os.getenv("USERPROFILE"),
        "PROGRAMFILES": os.getenv("PROGRAMFILES"),
        "PROGRAMFILES(X86)": os.getenv("PROGRAMFILES(X86)"),
    }
    raw = str(path)
    for key, value in env_map.items():
        if key in raw:
            if not value:
                return None
            raw = raw.replace(key, value)
    return Path(raw)


def get_all_profiles(browser: str) -> List[Dict]:
    """
    Get all user profiles for a browser.
    
    Returns list of dicts with profile name and paths.
    """
    config = BROWSER_CONFIG.get(browser)
    if not config:
        return []
    
    if config["type"] == "firefox":
        return _get_firefox_profiles(config)
    
    # Chromium-based browsers
    return _get_chromium_profiles(config)


def _get_chromium_profiles(config: Dict) -> List[Dict]:
    """Get all Chromium profiles."""
    profiles = []
    
    # Get user data dir
    user_data_dir = config.get("user_data_dir")
    if not user_data_dir:
        # Try to derive from local_state
        local_state = config.get("local_state")
        if local_state:
            resolved = resolve_path(local_state)
            if resolved:
                user_data_dir = resolved.parent
    else:
        user_data_dir = resolve_path(user_data_dir)
    
    if not user_data_dir or not user_data_dir.exists():
        return profiles
    
    # Find all profile directories
    profile_dirs = ["Default"]
    
    # Add numbered profiles (Profile 1, Profile 2, etc.)
    for item in user_data_dir.iterdir():
        if item.is_dir():
            name = item.name
            if name.startswith("Profile ") or name == "Guest Profile":
                profile_dirs.append(name)
    
    for profile_name in profile_dirs:
        profile_dir = user_data_dir / profile_name
        if not profile_dir.exists():
            continue
        
        cookies_paths = [
            profile_dir / "Cookies",
            profile_dir / "Network" / "Cookies",
        ]
        
        for cookies_path in cookies_paths:
            if cookies_path.exists():
                profiles.append({
                    "name": profile_name,
                    "cookies_path": cookies_path,
                    "profile_dir": profile_dir,
                })
                break
    
    return profiles


def _get_firefox_profiles(config: Dict) -> List[Dict]:
    """Get all Firefox profiles."""
    profiles = []
    
    if config.get("is_single_profile"):
        # Special case for Tor Browser etc.
        profiles_path = resolve_path(config["profiles_path"])
        if profiles_path and profiles_path.exists():
            cookie_file = profiles_path / config["cookie_file"]
            if cookie_file.exists():
                profiles.append({
                    "name": "default",
                    "cookies_path": cookie_file,
                    "profile_dir": profiles_path,
                })
        return profiles
    
    profiles_path = resolve_path(config["profiles_path"])
    if not profiles_path or not profiles_path.exists():
        return profiles
    
    # Find all profile directories (they end with .default or random.name)
    for item in profiles_path.iterdir():
        if item.is_dir():
            cookie_file = item / config["cookie_file"]
            if cookie_file.exists():
                profiles.append({
                    "name": item.name,
                    "cookies_path": cookie_file,
                    "profile_dir": item,
                })
    
    return profiles


def get_installed_browsers() -> List[str]:
    """Get list of browsers that appear to be installed."""
    installed = []
    
    for browser_id, config in BROWSER_CONFIG.items():
        if config["type"] == "chromium":
            local_state = config.get("local_state")
            if local_state:
                resolved = resolve_path(local_state)
                if resolved and resolved.exists():
                    installed.append(browser_id)
                    continue
            
            # Check cookie paths
            for cookie_path in config.get("cookie_paths", []):
                resolved = resolve_path(cookie_path)
                if resolved and resolved.exists():
                    installed.append(browser_id)
                    break
        
        elif config["type"] == "firefox":
            profiles_path = config.get("profiles_path")
            if profiles_path:
                resolved = resolve_path(profiles_path)
                if resolved and resolved.exists():
                    installed.append(browser_id)
    
    return installed
