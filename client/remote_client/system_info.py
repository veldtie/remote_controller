"""System information collection for the remote client."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
from ctypes import wintypes

SYSTEM_INFO_FILENAME = "system_info.json"


class _VSFixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def _truthy_env(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _resolve_system_info_path() -> str:
    env_path = os.getenv("RC_SYSTEM_INFO_PATH")
    if env_path:
        return os.path.expanduser(env_path)
    return os.path.join(
        os.path.expanduser("~"),
        ".remote_controller",
        SYSTEM_INFO_FILENAME,
    )


def _hidden_subprocess_kwargs() -> dict[str, object]:
    if platform.system() != "Windows":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    return {"startupinfo": startup, "creationflags": subprocess.CREATE_NO_WINDOW}


def _registry_app_paths(exe_name: str) -> list[str]:
    if platform.system() != "Windows" or not exe_name:
        return []
    try:
        import winreg
    except ImportError:
        return []
    paths: list[str] = []
    subkey = fr"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    views = (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY)
    for root in roots:
        for view in views:
            try:
                with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    if value:
                        paths.append(str(value))
            except OSError:
                continue
    return list(dict.fromkeys(paths))


def _iter_uninstall_entries() -> list[dict[str, str]]:
    if platform.system() != "Windows":
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


def _uninstall_candidates(
    entries: list[dict[str, str]],
    keywords: list[str],
    exe_names: list[str],
) -> tuple[list[str], str]:
    if not keywords:
        return [], ""
    matches: list[dict[str, str]] = []
    lowered = [value.lower() for value in keywords if value]
    for entry in entries:
        name = entry.get("display_name", "").lower()
        if not name:
            continue
        if any(key in name for key in lowered):
            matches.append(entry)
    candidates: list[str] = []
    version = ""
    for entry in matches:
        if not version:
            version = entry.get("display_version", "") or ""
        icon_path = _extract_exe_path(entry.get("display_icon", ""))
        if icon_path:
            candidates.append(icon_path)
        location = entry.get("install_location", "")
        if location:
            for exe_name in exe_names:
                candidates.append(os.path.join(location, exe_name))
    return list(dict.fromkeys(candidates)), version


def _resolve_executable(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        expanded = os.path.expandvars(os.path.expanduser(candidate))
        if os.path.isabs(expanded) and os.path.isfile(expanded):
            return expanded
        resolved = shutil.which(expanded)
        if resolved:
            return resolved
    return None


def _get_file_version(path: str) -> str:
    if platform.system() != "Windows" or not path:
        return ""
    try:
        version = ctypes.windll.version
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [
            wintypes.LPCVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.UINT),
        ]
        version.VerQueryValueW.restype = wintypes.BOOL

        handle = wintypes.DWORD()
        size = version.GetFileVersionInfoSizeW(path, ctypes.byref(handle))
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buffer):
            return ""
        value_ptr = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(value_ptr), ctypes.byref(length)):
            return ""
        if not value_ptr:
            return ""
        info = ctypes.cast(value_ptr, ctypes.POINTER(_VSFixedFileInfo)).contents
        major = info.dwFileVersionMS >> 16
        minor = info.dwFileVersionMS & 0xFFFF
        build = info.dwFileVersionLS >> 16
        revision = info.dwFileVersionLS & 0xFFFF
        return f"{major}.{minor}.{build}.{revision}"
    except Exception:
        return ""


def _collect_installed_browsers() -> list[dict[str, str]]:
    if platform.system() != "Windows":
        return []
    local_app_data = os.getenv("LOCALAPPDATA", "")
    app_data = os.getenv("APPDATA", "")
    program_files = os.getenv("PROGRAMFILES", "")
    program_files_x86 = os.getenv("PROGRAMFILES(X86)", "")
    definitions: list[dict[str, object]] = [
        {
            "id": "chrome",
            "name": "Chrome",
            "exe_names": ["chrome.exe"],
            "paths": [
                os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "keywords": ["google chrome"],
        },
        {
            "id": "safari",
            "name": "Safari",
            "exe_names": ["safari.exe"],
            "paths": [
                os.path.join(program_files, "Safari", "Safari.exe"),
                os.path.join(program_files_x86, "Safari", "Safari.exe"),
            ],
            "keywords": ["safari"],
        },
        {
            "id": "edge",
            "name": "Edge",
            "exe_names": ["msedge.exe"],
            "paths": [
                os.path.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            ],
            "keywords": ["microsoft edge"],
        },
        {
            "id": "firefox",
            "name": "Firefox",
            "exe_names": ["firefox.exe"],
            "paths": [
                os.path.join(program_files, "Mozilla Firefox", "firefox.exe"),
                os.path.join(program_files_x86, "Mozilla Firefox", "firefox.exe"),
            ],
            "keywords": ["mozilla firefox", "firefox"],
        },
        {
            "id": "samsung_internet",
            "name": "Samsung Internet",
            "exe_names": ["samsunginternet.exe"],
            "paths": [],
            "keywords": ["samsung internet"],
        },
        {
            "id": "opera",
            "name": "Opera",
            "exe_names": ["launcher.exe", "opera.exe"],
            "paths": [
                os.path.join(app_data, "Opera Software", "Opera Stable", "launcher.exe"),
                os.path.join(app_data, "Opera Software", "Opera Stable", "opera.exe"),
                os.path.join(local_app_data, "Programs", "Opera", "launcher.exe"),
                os.path.join(program_files, "Opera", "launcher.exe"),
                os.path.join(program_files_x86, "Opera", "launcher.exe"),
            ],
            "keywords": ["opera"],
        },
        {
            "id": "brave",
            "name": "Brave",
            "exe_names": ["brave.exe"],
            "paths": [
                os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ],
            "keywords": ["brave"],
        },
        {
            "id": "uc_browser",
            "name": "UC Browser",
            "exe_names": ["ucbrowser.exe"],
            "paths": [
                os.path.join(local_app_data, "UCBrowser", "UCBrowser.exe"),
                os.path.join(program_files, "UCBrowser", "UCBrowser.exe"),
                os.path.join(program_files_x86, "UCBrowser", "UCBrowser.exe"),
            ],
            "keywords": ["uc browser", "ucbrowser"],
        },
        {
            "id": "huawei_browser",
            "name": "Huawei Browser",
            "exe_names": ["huaweibrowser.exe"],
            "paths": [
                os.path.join(local_app_data, "Huawei", "Browser", "HuaweiBrowser.exe"),
                os.path.join(program_files, "Huawei", "Browser", "HuaweiBrowser.exe"),
                os.path.join(program_files_x86, "Huawei", "Browser", "HuaweiBrowser.exe"),
            ],
            "keywords": ["huawei browser"],
        },
        {
            "id": "dolphin_anty",
            "name": "Dolphin Anty",
            "exe_names": ["dolphinanty.exe", "dolphin anty.exe"],
            "paths": [
                os.path.join(local_app_data, "Dolphin Anty", "Dolphin Anty.exe"),
                os.path.join(program_files, "Dolphin Anty", "Dolphin Anty.exe"),
                os.path.join(program_files_x86, "Dolphin Anty", "Dolphin Anty.exe"),
            ],
            "keywords": ["dolphin anty"],
        },
        {
            "id": "octo",
            "name": "Octo Browser",
            "exe_names": ["octobrowser.exe", "octo browser.exe"],
            "paths": [
                os.path.join(local_app_data, "Octo Browser", "Octo Browser.exe"),
                os.path.join(program_files, "Octo Browser", "Octo Browser.exe"),
                os.path.join(program_files_x86, "Octo Browser", "Octo Browser.exe"),
            ],
            "keywords": ["octo browser", "octobrowser"],
        },
        {
            "id": "adspower",
            "name": "AdsPower",
            "exe_names": ["adspower.exe", "adspowerbrowser.exe"],
            "paths": [
                os.path.join(local_app_data, "AdsPower", "AdsPower.exe"),
                os.path.join(program_files, "AdsPower", "AdsPower.exe"),
                os.path.join(program_files_x86, "AdsPower", "AdsPower.exe"),
            ],
            "keywords": ["adspower"],
        },
        {
            "id": "linken_sphere_2",
            "name": "Linken Sphere 2",
            "exe_names": ["linken sphere 2.exe", "linkensphere2.exe"],
            "paths": [
                os.path.join(local_app_data, "Linken Sphere 2", "Linken Sphere 2.exe"),
                os.path.join(program_files, "Linken Sphere 2", "Linken Sphere 2.exe"),
                os.path.join(program_files_x86, "Linken Sphere 2", "Linken Sphere 2.exe"),
            ],
            "keywords": ["linken sphere 2", "linken sphere", "linken sfera 2", "linken sfera"],
        },
    ]
    uninstall_entries = _iter_uninstall_entries()
    results: list[dict[str, str]] = []
    for definition in definitions:
        exe_names = list(definition.get("exe_names") or [])
        paths = list(definition.get("paths") or [])
        keywords = list(definition.get("keywords") or [])
        candidates: list[str] = []
        for exe_name in exe_names:
            candidates.extend(_registry_app_paths(exe_name))
        uninstall_paths, uninstall_version = _uninstall_candidates(
            uninstall_entries,
            keywords,
            exe_names,
        )
        candidates.extend(uninstall_paths)
        candidates.extend(paths)
        candidates.extend(exe_names)
        exe_path = _resolve_executable(list(dict.fromkeys(candidates)))
        version = _get_file_version(exe_path) if exe_path else ""
        if not version:
            version = uninstall_version
        if not exe_path and not version:
            continue
        entry = {
            "id": str(definition.get("id") or ""),
            "name": str(definition.get("name") or ""),
        }
        if version:
            entry["version"] = version
        results.append(entry)
    return results


def _wmic_query_list(command: list[str], field: str) -> list[str]:
    try:
        output = subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.DEVNULL,
            **_hidden_subprocess_kwargs(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    values: list[str] = []
    field_key = field.strip().lower()
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().lower() == field_key:
            cleaned = value.strip()
            if cleaned:
                values.append(cleaned)
    return values


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return ""


def _get_pc_name() -> str:
    wmic_values = _wmic_query_list(
        ["wmic", "computersystem", "get", "Name", "/value"],
        "Name",
    )
    name = _first_non_empty(wmic_values)
    if name:
        return name
    env_name = os.getenv("COMPUTERNAME", "").strip()
    if env_name:
        return env_name
    return platform.node().strip()


def _get_cpu_name() -> str:
    wmic_values = _wmic_query_list(
        ["wmic", "cpu", "get", "Name", "/value"],
        "Name",
    )
    name = _first_non_empty(wmic_values)
    if name:
        return name
    env_cpu = os.getenv("PROCESSOR_IDENTIFIER", "").strip()
    if env_cpu:
        return env_cpu
    return platform.processor().strip()


def _get_gpu_name() -> str:
    wmic_values = _wmic_query_list(
        ["wmic", "path", "win32_videocontroller", "get", "Name", "/value"],
        "Name",
    )
    unique = []
    for value in wmic_values:
        cleaned = value.strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return ", ".join(unique)


def _get_total_memory_bytes() -> int | None:
    if platform.system() != "Windows":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPhys)


def _get_drive_totals() -> tuple[int, int] | None:
    if platform.system() != "Windows":
        return None
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    if not bitmask:
        return None
    total_bytes = 0
    free_bytes = 0
    for index in range(26):
        if not (bitmask & (1 << index)):
            continue
        drive = f"{chr(65 + index)}:\\"
        drive_type = kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive))
        # DRIVE_FIXED = 3
        if drive_type != 3:
            continue
        total = ctypes.c_ulonglong(0)
        free = ctypes.c_ulonglong(0)
        if kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(drive),
            None,
            ctypes.byref(total),
            ctypes.byref(free),
        ):
            total_bytes += int(total.value)
            free_bytes += int(free.value)
    if total_bytes <= 0:
        return None
    return total_bytes, free_bytes


def _format_gb(value_bytes: int) -> str:
    gb = value_bytes / (1024**3)
    if gb < 1:
        return f"{gb:.1f} GB"
    if gb < 10:
        return f"{gb:.1f} GB"
    return f"{gb:.0f} GB"


def _format_storage(total_bytes: int, free_bytes: int | None) -> str:
    total_label = _format_gb(total_bytes)
    if free_bytes is None or free_bytes <= 0 or free_bytes > total_bytes:
        return total_label
    used_bytes = max(0, total_bytes - free_bytes)
    used_label = _format_gb(used_bytes)
    return f"{used_label} / {total_label}"


def collect_system_info() -> dict[str, object]:
    info: dict[str, object] = {}
    pc_name = _get_pc_name()
    if pc_name:
        info["pc_name"] = pc_name
    cpu_name = _get_cpu_name()
    if cpu_name:
        info["cpu"] = cpu_name
    gpu_name = _get_gpu_name()
    if gpu_name:
        info["gpu"] = gpu_name
    mem_total = _get_total_memory_bytes()
    if mem_total:
        info["ram"] = _format_gb(mem_total)
    drives = _get_drive_totals()
    if drives:
        total_bytes, free_bytes = drives
        info["storage"] = _format_storage(total_bytes, free_bytes)
    info["browsers"] = _collect_installed_browsers()
    return info


def _load_cached_system_info(path: str) -> dict[str, object] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    cleaned: dict[str, object] = {}
    for key, value in data.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if isinstance(value, (list, dict)):
            cleaned[key_text] = value
            continue
        if value is None:
            continue
        value_text = str(value).strip()
        if value_text:
            cleaned[key_text] = value_text
    return cleaned


def _needs_refresh(cached: dict[str, object]) -> bool:
    storage = str(cached.get("storage") or "")
    if "%" in storage or " of " in storage:
        return True
    if "browsers" not in cached:
        return True
    return False


def _save_system_info(path: str, info: dict[str, object]) -> None:
    if not info:
        return
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(info, handle, ensure_ascii=False, indent=2)
    except OSError:
        return


def load_or_collect_system_info() -> dict[str, object]:
    if _truthy_env("RC_DISABLE_SYSTEM_INFO"):
        return {}
    path = _resolve_system_info_path()
    if not _truthy_env("RC_REFRESH_SYSTEM_INFO"):
        cached = _load_cached_system_info(path)
        if cached and not _needs_refresh(cached):
            return cached
    info = collect_system_info()
    _save_system_info(path, info)
    return info
