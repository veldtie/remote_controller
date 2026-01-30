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
