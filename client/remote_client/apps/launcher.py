from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


_APP_ALIASES: dict[str, str] = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "safari": "safari",
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
    "samsung internet": "samsung_internet",
    "samsung": "samsung_internet",
    "opera": "opera",
    "brave": "brave",
    "brave browser": "brave",
    "uc browser": "uc_browser",
    "ucbrowser": "uc_browser",
    "huawei browser": "huawei_browser",
    "dolphin anty": "dolphin_anty",
    "dolphin anty browser": "dolphin_anty",
    "octo": "octo",
    "octo browser": "octo",
    "octobrowser": "octo",
    "octa": "octo",
    "adspower": "adspower",
    "ads power": "adspower",
    "linken sphere 2": "linken_sphere_2",
    "linken sphere": "linken_sphere_2",
    "linken sfera 2": "linken_sphere_2",
    "linken sfera": "linken_sphere_2",
}

_UNINSTALL_CACHE: list[dict[str, str]] | None = None


def _iter_uninstall_entries() -> list[dict[str, str]]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    entries: list[dict[str, str]] = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    subkey = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    views = (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY)

    def _read_value(key, name: str) -> str:
        try:
            value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            return ""
        return str(value or "").strip()

    for root in roots:
        for view in views:
            try:
                with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | view) as base:
                    try:
                        total = winreg.QueryInfoKey(base)[0]
                    except OSError:
                        total = 0
                    for idx in range(total):
                        try:
                            name = winreg.EnumKey(base, idx)
                        except OSError:
                            continue
                        try:
                            with winreg.OpenKey(base, name) as entry_key:
                                display_name = _read_value(entry_key, "DisplayName")
                                if not display_name:
                                    continue
                                entries.append(
                                    {
                                        "display_name": display_name,
                                        "display_version": _read_value(entry_key, "DisplayVersion"),
                                        "install_location": _read_value(entry_key, "InstallLocation"),
                                        "display_icon": _read_value(entry_key, "DisplayIcon"),
                                    }
                                )
                        except OSError:
                            continue
            except OSError:
                continue
    return entries


def _get_uninstall_entries() -> list[dict[str, str]]:
    global _UNINSTALL_CACHE
    if _UNINSTALL_CACHE is None:
        _UNINSTALL_CACHE = _iter_uninstall_entries()
    return _UNINSTALL_CACHE


def _extract_exe_path(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().strip('"')
    match = re.search(r"([A-Za-z]:\\[^\"']+?\.exe)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1)
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0].strip().strip('"')
    match = re.search(r"([A-Za-z]:\\[^\"']+?\.exe)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1)
    return cleaned if cleaned.lower().endswith(".exe") else ""


def _uninstall_candidates(keywords: list[str], exe_names: list[str]) -> list[str]:
    if not keywords:
        return []
    entries = _get_uninstall_entries()
    lowered = [value.lower() for value in keywords if value]
    candidates: list[str] = []
    for entry in entries:
        name = entry.get("display_name", "").lower()
        if not name:
            continue
        if not any(key in name for key in lowered):
            continue
        icon_path = _extract_exe_path(entry.get("display_icon", ""))
        if icon_path:
            candidates.append(icon_path)
        location = entry.get("install_location", "")
        if location:
            for exe_name in exe_names:
                candidates.append(os.path.join(location, exe_name))
    return list(dict.fromkeys(candidates))


_LOCAL_APP_DATA = os.getenv("LOCALAPPDATA", "")
_APP_DATA = os.getenv("APPDATA", "")
_PROGRAM_FILES = os.getenv("PROGRAMFILES", "")
_PROGRAM_FILES_X86 = os.getenv("PROGRAMFILES(X86)", "")

_APP_DEFINITIONS: dict[str, dict[str, list[str]]] = {
    "chrome": {
        "exe_names": ["chrome.exe"],
        "paths": [
            os.path.join(_PROGRAM_FILES, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(_LOCAL_APP_DATA, "Google", "Chrome", "Application", "chrome.exe"),
        ],
        "keywords": ["google chrome"],
    },
    "safari": {
        "exe_names": ["safari.exe"],
        "paths": [
            os.path.join(_PROGRAM_FILES, "Safari", "Safari.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Safari", "Safari.exe"),
        ],
        "keywords": ["safari"],
    },
    "edge": {
        "exe_names": ["msedge.exe"],
        "paths": [
            os.path.join(_PROGRAM_FILES, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(_LOCAL_APP_DATA, "Microsoft", "Edge", "Application", "msedge.exe"),
        ],
        "keywords": ["microsoft edge"],
    },
    "firefox": {
        "exe_names": ["firefox.exe"],
        "paths": [
            os.path.join(_PROGRAM_FILES, "Mozilla Firefox", "firefox.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Mozilla Firefox", "firefox.exe"),
        ],
        "keywords": ["mozilla firefox", "firefox"],
    },
    "samsung_internet": {
        "exe_names": ["samsunginternet.exe"],
        "paths": [],
        "keywords": ["samsung internet"],
    },
    "opera": {
        "exe_names": ["launcher.exe", "opera.exe"],
        "paths": [
            os.path.join(_APP_DATA, "Opera Software", "Opera Stable", "launcher.exe"),
            os.path.join(_LOCAL_APP_DATA, "Programs", "Opera", "launcher.exe"),
            os.path.join(_LOCAL_APP_DATA, "Opera", "launcher.exe"),
            os.path.join(_PROGRAM_FILES, "Opera", "launcher.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Opera", "launcher.exe"),
        ],
        "keywords": ["opera"],
    },
    "brave": {
        "exe_names": ["brave.exe"],
        "paths": [
            os.path.join(_PROGRAM_FILES, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(_PROGRAM_FILES_X86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(_LOCAL_APP_DATA, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ],
        "keywords": ["brave"],
    },
    "uc_browser": {
        "exe_names": ["ucbrowser.exe"],
        "paths": [
            os.path.join(_LOCAL_APP_DATA, "UCBrowser", "UCBrowser.exe"),
            os.path.join(_PROGRAM_FILES, "UCBrowser", "UCBrowser.exe"),
            os.path.join(_PROGRAM_FILES_X86, "UCBrowser", "UCBrowser.exe"),
        ],
        "keywords": ["uc browser", "ucbrowser"],
    },
    "huawei_browser": {
        "exe_names": ["huaweibrowser.exe"],
        "paths": [
            os.path.join(_LOCAL_APP_DATA, "Huawei", "Browser", "HuaweiBrowser.exe"),
            os.path.join(_PROGRAM_FILES, "Huawei", "Browser", "HuaweiBrowser.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Huawei", "Browser", "HuaweiBrowser.exe"),
        ],
        "keywords": ["huawei browser"],
    },
    "dolphin_anty": {
        "exe_names": ["dolphinanty.exe", "dolphin anty.exe"],
        "paths": [
            os.path.join(_LOCAL_APP_DATA, "Dolphin Anty", "Dolphin Anty.exe"),
            os.path.join(_PROGRAM_FILES, "Dolphin Anty", "Dolphin Anty.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Dolphin Anty", "Dolphin Anty.exe"),
        ],
        "keywords": ["dolphin anty"],
    },
    "octo": {
        "exe_names": ["octobrowser.exe", "octo browser.exe"],
        "paths": [
            os.path.join(_LOCAL_APP_DATA, "Octo Browser", "Octo Browser.exe"),
            os.path.join(_PROGRAM_FILES, "Octo Browser", "Octo Browser.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Octo Browser", "Octo Browser.exe"),
        ],
        "keywords": ["octo browser", "octobrowser"],
    },
    "adspower": {
        "exe_names": ["adspower.exe", "adspowerbrowser.exe"],
        "paths": [
            os.path.join(_LOCAL_APP_DATA, "AdsPower", "AdsPower.exe"),
            os.path.join(_PROGRAM_FILES, "AdsPower", "AdsPower.exe"),
            os.path.join(_PROGRAM_FILES_X86, "AdsPower", "AdsPower.exe"),
        ],
        "keywords": ["adspower"],
    },
    "linken_sphere_2": {
        "exe_names": ["linken sphere 2.exe", "linkensphere2.exe"],
        "paths": [
            os.path.join(_LOCAL_APP_DATA, "Linken Sphere 2", "Linken Sphere 2.exe"),
            os.path.join(_PROGRAM_FILES, "Linken Sphere 2", "Linken Sphere 2.exe"),
            os.path.join(_PROGRAM_FILES_X86, "Linken Sphere 2", "Linken Sphere 2.exe"),
        ],
        "keywords": ["linken sphere 2", "linken sphere", "linken sfera 2", "linken sfera"],
    },
}


def _candidate_paths(app_key: str) -> list[str]:
    definition = _APP_DEFINITIONS.get(app_key)
    if not definition:
        return [app_key]
    exe_names = list(definition.get("exe_names") or [])
    candidates: list[str] = []
    candidates.extend(_uninstall_candidates(definition.get("keywords", []), exe_names))
    candidates.extend(definition.get("paths") or [])
    candidates.extend(exe_names)
    return candidates or [app_key]


def _iter_candidates(app_name: str) -> Iterable[str]:
    normalized = app_name.strip().lower()
    if not normalized:
        return []
    alias = _APP_ALIASES.get(normalized, normalized)
    return _candidate_paths(alias)


def _resolve_executable(app_name: str) -> str | None:
    if not app_name:
        return None
    maybe_path = Path(app_name)
    if maybe_path.exists():
        return str(maybe_path)
    for candidate in _iter_candidates(app_name):
        if not candidate:
            continue
        if os.path.isabs(candidate) and Path(candidate).exists():
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def resolve_app_executable(app_name: str) -> str | None:
    return _resolve_executable(app_name)


def _build_startup(hidden: bool) -> tuple[int, subprocess.STARTUPINFO | None]:
    if os.name != "nt":
        return 0, None
    creationflags = 0
    startupinfo = None
    if hidden:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags |= subprocess.CREATE_NO_WINDOW
    return creationflags, startupinfo


def launch_app(app_name: str, hidden: bool = True) -> bool:
    exe_path = resolve_app_executable(app_name)
    if not exe_path:
        logger.warning("Unknown app or executable not found: %s", app_name)
        return False
    creationflags, startupinfo = _build_startup(hidden)
    try:
        subprocess.Popen(
            [exe_path],
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        return True
    except Exception:
        logger.exception("Failed to launch app: %s", app_name)
        return False
