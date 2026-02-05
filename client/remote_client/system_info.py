"""System information collection for the remote client."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess

SYSTEM_INFO_FILENAME = "system_info.json"


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


def collect_system_info() -> dict[str, str]:
    info: dict[str, str] = {}
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
    return info


def _load_cached_system_info(path: str) -> dict[str, str] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): str(v) for k, v in data.items() if k and v}


def _needs_refresh(cached: dict[str, str]) -> bool:
    storage = str(cached.get("storage") or "")
    if "%" in storage or " of " in storage:
        return True
    return False


def _save_system_info(path: str, info: dict[str, str]) -> None:
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


def load_or_collect_system_info() -> dict[str, str]:
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
