from __future__ import annotations

import os
from pathlib import Path

BROWSER_CONFIG = {
    "chrome": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "Google"
            / "Chrome"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Google" / "Chrome" / "User Data" / "Local State",
    },
    "edge": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "Microsoft"
            / "Edge"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Microsoft" / "Edge" / "User Data" / "Local State",
    },
    "brave": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA")
            / "BraveSoftware"
            / "Brave-Browser"
            / "User Data"
            / "Default"
            / "Cookies",
            Path("LOCALAPPDATA")
            / "BraveSoftware"
            / "Brave-Browser"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA")
        / "BraveSoftware"
        / "Brave-Browser"
        / "User Data"
        / "Local State",
    },
    "opera": {
        "type": "chromium",
        "cookie_paths": [
            Path("APPDATA") / "Opera Software" / "Opera Stable" / "Cookies",
            Path("APPDATA") / "Opera Software" / "Opera Stable" / "Network" / "Cookies",
        ],
        "local_state": Path("APPDATA") / "Opera Software" / "Opera Stable" / "Local State",
    },
    "uc_browser": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "UCBrowser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "UCBrowser"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "UCBrowser" / "User Data" / "Local State",
    },
    "huawei_browser": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Huawei" / "Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "Huawei"
            / "Browser"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Huawei" / "Browser" / "User Data" / "Local State",
    },
    "samsung_internet": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA")
            / "Samsung"
            / "Samsung Internet"
            / "User Data"
            / "Default"
            / "Cookies",
            Path("LOCALAPPDATA")
            / "Samsung"
            / "Samsung Internet"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA")
        / "Samsung"
        / "Samsung Internet"
        / "User Data"
        / "Local State",
    },
    "dolphin_anty": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Dolphin Anty" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "Dolphin Anty"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
            Path("APPDATA") / "Dolphin Anty" / "User Data" / "Default" / "Cookies",
            Path("APPDATA")
            / "Dolphin Anty"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Dolphin Anty" / "User Data" / "Local State",
    },
    "octo": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Octo Browser" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "Octo Browser"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
            Path("APPDATA") / "Octo Browser" / "User Data" / "Default" / "Cookies",
            Path("APPDATA")
            / "Octo Browser"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Octo Browser" / "User Data" / "Local State",
    },
    "adspower": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "AdsPower" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "AdsPower"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
            Path("APPDATA") / "AdsPower" / "User Data" / "Default" / "Cookies",
            Path("APPDATA")
            / "AdsPower"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "AdsPower" / "User Data" / "Local State",
    },
    "linken_sphere_2": {
        "type": "chromium",
        "cookie_paths": [
            Path("LOCALAPPDATA") / "Linken Sphere 2" / "User Data" / "Default" / "Cookies",
            Path("LOCALAPPDATA")
            / "Linken Sphere 2"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
            Path("APPDATA") / "Linken Sphere 2" / "User Data" / "Default" / "Cookies",
            Path("APPDATA")
            / "Linken Sphere 2"
            / "User Data"
            / "Default"
            / "Network"
            / "Cookies",
        ],
        "local_state": Path("LOCALAPPDATA") / "Linken Sphere 2" / "User Data" / "Local State",
    },
    "firefox": {
        "type": "firefox",
        "profiles_path": Path("APPDATA") / "Mozilla" / "Firefox" / "Profiles",
        "cookie_file": "cookies.sqlite",
    },
}


def resolve_path(path: Path) -> Path | None:
    env_map = {
        "LOCALAPPDATA": os.getenv("LOCALAPPDATA"),
        "APPDATA": os.getenv("APPDATA"),
    }
    raw = str(path)
    for key, value in env_map.items():
        if key in raw:
            if not value:
                return None
            raw = raw.replace(key, value)
    return Path(raw)
