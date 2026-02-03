"""App launcher utilities for remote sessions."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Iterable

logger = logging.getLogger(__name__)

WINDOWS_APP_PATHS: dict[str, list[str]] = {
    "chrome": [
        r"{pf}\Google\Chrome\Application\chrome.exe",
        r"{pf86}\Google\Chrome\Application\chrome.exe",
        r"{local}\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"{pf}\Microsoft\Edge\Application\msedge.exe",
        r"{pf86}\Microsoft\Edge\Application\msedge.exe",
        r"{local}\Microsoft\Edge\Application\msedge.exe",
    ],
    "brave": [
        r"{pf}\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"{pf86}\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"{local}\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "opera": [
        r"{pf}\Opera\launcher.exe",
        r"{pf86}\Opera\launcher.exe",
        r"{local}\Programs\Opera\launcher.exe",
        r"{pf}\Opera GX\launcher.exe",
        r"{pf86}\Opera GX\launcher.exe",
        r"{local}\Programs\Opera GX\launcher.exe",
    ],
    "firefox": [
        r"{pf}\Mozilla Firefox\firefox.exe",
        r"{pf86}\Mozilla Firefox\firefox.exe",
        r"{local}\Mozilla Firefox\firefox.exe",
    ],
    "yandex": [
        r"{pf}\Yandex\YandexBrowser\Application\browser.exe",
        r"{pf86}\Yandex\YandexBrowser\Application\browser.exe",
        r"{local}\Yandex\YandexBrowser\Application\browser.exe",
    ],
}


def launch_app(app_name: str, hidden: bool = False) -> None:
    """Launch an application by name."""
    name = str(app_name or "").strip()
    if not name:
        raise ValueError("Empty app name")

    if os.name == "nt":
        _launch_windows(name, hidden=hidden)
        return

    _launch_posix(name)


def _launch_windows(name: str, hidden: bool) -> None:
    key = name.lower()
    path = _resolve_windows_path(key)
    creationflags = 0
    startupinfo = None
    if hidden:
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

    if path:
        logger.info("Launching app via path: %s", path)
        subprocess.Popen([path], creationflags=creationflags, startupinfo=startupinfo)
        return

    if shutil.which(name):
        logger.info("Launching app via PATH: %s", name)
        subprocess.Popen([name], creationflags=creationflags, startupinfo=startupinfo)
        return

    logger.info("Launching app via shell start: %s", name)
    subprocess.Popen(
        ["cmd", "/c", "start", "", name],
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


def _launch_posix(name: str) -> None:
    if shutil.which(name):
        subprocess.Popen([name])
        return
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", name])
        return
    logger.warning("No launcher available for app: %s", name)


def _resolve_windows_path(name: str) -> str | None:
    candidates = WINDOWS_APP_PATHS.get(name, [])
    if not candidates:
        return None
    resolved = _expand_windows_paths(candidates)
    for path in resolved:
        if path and os.path.exists(path):
            return path
    return None


def _expand_windows_paths(paths: Iterable[str]) -> list[str]:
    pf = os.getenv("ProgramFiles", "")
    pf86 = os.getenv("ProgramFiles(x86)", "")
    local = os.getenv("LOCALAPPDATA", "")
    resolved = []
    for template in paths:
        resolved.append(
            template.replace("{pf}", pf).replace("{pf86}", pf86).replace("{local}", local)
        )
    return resolved
