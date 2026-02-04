from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


_APP_ALIASES: dict[str, str] = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "brave": "brave",
    "brave browser": "brave",
    "opera": "opera",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
    "edge": "edge",
    "microsoft edge": "edge",
    "yandex": "yandex",
    "yandex browser": "yandex",
}


def _candidate_paths(app_key: str) -> list[str]:
    local_app_data = os.getenv("LOCALAPPDATA", "")
    program_files = os.getenv("PROGRAMFILES", "")
    program_files_x86 = os.getenv("PROGRAMFILES(X86)", "")

    if app_key == "chrome":
        return [
            "chrome.exe",
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    if app_key == "brave":
        return [
            "brave.exe",
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
    if app_key == "opera":
        return [
            "launcher.exe",
            "opera.exe",
            os.path.join(program_files, "Opera", "launcher.exe"),
            os.path.join(program_files_x86, "Opera", "launcher.exe"),
            os.path.join(local_app_data, "Programs", "Opera", "launcher.exe"),
            os.path.join(local_app_data, "Opera", "launcher.exe"),
        ]
    if app_key == "firefox":
        return [
            "firefox.exe",
            os.path.join(program_files, "Mozilla Firefox", "firefox.exe"),
            os.path.join(program_files_x86, "Mozilla Firefox", "firefox.exe"),
        ]
    if app_key == "edge":
        return [
            "msedge.exe",
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    if app_key == "yandex":
        return [
            "browser.exe",
            os.path.join(local_app_data, "Yandex", "YandexBrowser", "Application", "browser.exe"),
            os.path.join(program_files, "Yandex", "YandexBrowser", "Application", "browser.exe"),
            os.path.join(program_files_x86, "Yandex", "YandexBrowser", "Application", "browser.exe"),
        ]
    return [app_key]


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
    exe_path = _resolve_executable(app_name)
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
