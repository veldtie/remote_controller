"""Launch common applications on the remote host."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


_CHROMIUM_APPS = {"chrome", "edge", "brave", "opera", "yandex"}


def _env_path(env_name: str, *parts: str) -> Path | None:
    root = os.environ.get(env_name)
    if not root:
        return None
    return Path(root, *parts)


def _candidate_paths(app_key: str) -> list[Path]:
    if app_key == "chrome":
        return [
            _env_path("LOCALAPPDATA", "Google", "Chrome", "Application", "chrome.exe"),
            _env_path("PROGRAMFILES", "Google", "Chrome", "Application", "chrome.exe"),
            _env_path("PROGRAMFILES(X86)", "Google", "Chrome", "Application", "chrome.exe"),
        ]
    if app_key == "edge":
        return [
            _env_path("PROGRAMFILES(X86)", "Microsoft", "Edge", "Application", "msedge.exe"),
            _env_path("PROGRAMFILES", "Microsoft", "Edge", "Application", "msedge.exe"),
            _env_path("LOCALAPPDATA", "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    if app_key == "brave":
        return [
            _env_path(
                "PROGRAMFILES", "BraveSoftware", "Brave-Browser", "Application", "brave.exe"
            ),
            _env_path(
                "LOCALAPPDATA", "BraveSoftware", "Brave-Browser", "Application", "brave.exe"
            ),
            _env_path(
                "PROGRAMFILES(X86)",
                "BraveSoftware",
                "Brave-Browser",
                "Application",
                "brave.exe",
            ),
        ]
    if app_key == "opera":
        return [
            _env_path("LOCALAPPDATA", "Programs", "Opera", "launcher.exe"),
            _env_path("PROGRAMFILES", "Opera", "launcher.exe"),
            _env_path("PROGRAMFILES(X86)", "Opera", "launcher.exe"),
            _env_path("APPDATA", "Opera Software", "Opera Stable", "launcher.exe"),
            _env_path("APPDATA", "Opera Software", "Opera Stable", "opera.exe"),
        ]
    if app_key == "firefox":
        return [
            _env_path("PROGRAMFILES", "Mozilla Firefox", "firefox.exe"),
            _env_path("PROGRAMFILES(X86)", "Mozilla Firefox", "firefox.exe"),
            _env_path("LOCALAPPDATA", "Mozilla Firefox", "firefox.exe"),
        ]
    if app_key == "yandex":
        return [
            _env_path(
                "LOCALAPPDATA", "Yandex", "YandexBrowser", "Application", "browser.exe"
            ),
            _env_path(
                "PROGRAMFILES", "Yandex", "YandexBrowser", "Application", "browser.exe"
            ),
            _env_path(
                "PROGRAMFILES(X86)", "Yandex", "YandexBrowser", "Application", "browser.exe"
            ),
        ]
    return []


def _resolve_executable(app_key: str) -> str | None:
    env_override = os.getenv(f"RC_APP_{app_key.upper()}_PATH", "").strip()
    if env_override:
        candidate = Path(env_override)
        if candidate.exists():
            return str(candidate)
    for candidate in _candidate_paths(app_key):
        if candidate and candidate.exists():
            return str(candidate)
    lookup = shutil.which(app_key)
    if lookup:
        return lookup
    return None


def _normalize_app_name(app_name: str) -> str:
    value = (app_name or "").strip().lower()
    if value in {"msedge", "edge"}:
        return "edge"
    if value in {"google chrome", "chrome"}:
        return "chrome"
    if value in {"brave", "brave-browser", "brave browser"}:
        return "brave"
    if value in {"opera"}:
        return "opera"
    if value in {"mozilla", "firefox"}:
        return "firefox"
    if value in {"yandex", "yandexbrowser", "yandex browser"}:
        return "yandex"
    return value


def launch_app(app_name: str, hidden: bool = True) -> None:
    app_key = _normalize_app_name(app_name)
    if app_key not in {"chrome", "edge", "brave", "opera", "firefox", "yandex"}:
        raise ValueError(f"Unsupported app '{app_name}'.")
    executable = _resolve_executable(app_key)
    if not executable:
        raise FileNotFoundError(f"{app_name} executable not found.")

    args: list[str] = [executable]
    headless_enabled = os.getenv("RC_LAUNCH_HEADLESS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if hidden:
        if app_key in _CHROMIUM_APPS:
            args.extend(
                [
                    "--start-minimized",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
            )
            if headless_enabled:
                args.append("--headless=new")
        elif app_key == "firefox":
            if headless_enabled:
                args.append("-headless")

    creationflags = 0
    startupinfo = None
    if os.name == "nt" and hidden:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
        close_fds=os.name != "nt",
    )
