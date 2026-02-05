"""Process monitor to detect task manager and hide the application."""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

MONITORED_PROCESSES = {
    "taskmgr.exe",
    "procexp.exe",
    "procexp64.exe",
    "processhacker.exe",
    "perfmon.exe",
    "resmon.exe",
    "procmon.exe",
    "procmon64.exe",
}


class ProcessMonitor:
    """Monitors for task manager and similar processes, triggers hide callback."""

    def __init__(
        self,
        on_detected: Callable[[], None] | None = None,
        on_cleared: Callable[[], None] | None = None,
        check_interval: float = 0.5,
    ) -> None:
        self._on_detected = on_detected
        self._on_cleared = on_cleared
        self._check_interval = check_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._detected = False

    def start(self) -> None:
        if platform.system() != "Windows":
            logger.debug("Process monitor only supported on Windows.")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.debug("Process monitor started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.debug("Process monitor stopped.")

    def _check_processes(self) -> bool:
        """Check if any monitored process is running."""
        try:
            import ctypes.wintypes as wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            MAX_PATH = 260

            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi

            process_ids = (ctypes.c_ulong * 2048)()
            bytes_returned = ctypes.c_ulong()

            if not psapi.EnumProcesses(
                ctypes.byref(process_ids),
                ctypes.sizeof(process_ids),
                ctypes.byref(bytes_returned),
            ):
                return False

            num_processes = bytes_returned.value // ctypes.sizeof(ctypes.c_ulong)

            for i in range(num_processes):
                pid = process_ids[i]
                if pid == 0:
                    continue

                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not handle:
                    continue

                try:
                    exe_path = (ctypes.c_wchar * MAX_PATH)()
                    size = wintypes.DWORD(MAX_PATH)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, exe_path, ctypes.byref(size)):
                        exe_name = os.path.basename(exe_path.value).lower()
                        if exe_name in MONITORED_PROCESSES:
                            return True
                finally:
                    kernel32.CloseHandle(handle)

            return False
        except Exception as e:
            logger.debug("Process check failed: %s", e)
            return False

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                detected = self._check_processes()
                if detected and not self._detected:
                    self._detected = True
                    logger.debug("Task manager detected, triggering hide.")
                    if self._on_detected:
                        try:
                            self._on_detected()
                        except Exception:
                            logger.exception("on_detected callback failed")
                elif not detected and self._detected:
                    self._detected = False
                    logger.debug("Task manager closed, triggering show.")
                    if self._on_cleared:
                        try:
                            self._on_cleared()
                        except Exception:
                            logger.exception("on_cleared callback failed")
            except Exception:
                logger.exception("Monitor loop error")

            self._stop_event.wait(self._check_interval)


_console_hidden = False


def hide_console_window() -> None:
    """Hide the console window."""
    global _console_hidden
    if platform.system() != "Windows":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
            _console_hidden = True
            logger.debug("Console window hidden.")
    except Exception as e:
        logger.debug("Failed to hide console: %s", e)


def show_console_window() -> None:
    """Show the console window."""
    global _console_hidden
    if platform.system() != "Windows":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            _console_hidden = False
            logger.debug("Console window shown.")
    except Exception as e:
        logger.debug("Failed to show console: %s", e)


def suspend_current_process() -> None:
    """Suspend all threads of the current process except the monitor thread."""
    if platform.system() != "Windows":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        ntdll = ctypes.windll.ntdll

        current_pid = kernel32.GetCurrentProcessId()
        current_tid = kernel32.GetCurrentThreadId()

        THREAD_SUSPEND_RESUME = 0x0002
        
        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_ulong),
                ("cntUsage", ctypes.c_ulong),
                ("th32ThreadID", ctypes.c_ulong),
                ("th32OwnerProcessID", ctypes.c_ulong),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong),
            ]

        TH32CS_SNAPTHREAD = 0x00000004
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == -1:
            return

        try:
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)

            if kernel32.Thread32First(snapshot, ctypes.byref(te)):
                while True:
                    if te.th32OwnerProcessID == current_pid and te.th32ThreadID != current_tid:
                        thread_handle = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, te.th32ThreadID)
                        if thread_handle:
                            kernel32.SuspendThread(thread_handle)
                            kernel32.CloseHandle(thread_handle)
                    if not kernel32.Thread32Next(snapshot, ctypes.byref(te)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)

        logger.debug("Process threads suspended.")
    except Exception as e:
        logger.debug("Failed to suspend process: %s", e)


def resume_current_process() -> None:
    """Resume all threads of the current process."""
    if platform.system() != "Windows":
        return
    try:
        kernel32 = ctypes.windll.kernel32

        current_pid = kernel32.GetCurrentProcessId()
        current_tid = kernel32.GetCurrentThreadId()

        THREAD_SUSPEND_RESUME = 0x0002

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_ulong),
                ("cntUsage", ctypes.c_ulong),
                ("th32ThreadID", ctypes.c_ulong),
                ("th32OwnerProcessID", ctypes.c_ulong),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong),
            ]

        TH32CS_SNAPTHREAD = 0x00000004
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == -1:
            return

        try:
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)

            if kernel32.Thread32First(snapshot, ctypes.byref(te)):
                while True:
                    if te.th32OwnerProcessID == current_pid and te.th32ThreadID != current_tid:
                        thread_handle = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, te.th32ThreadID)
                        if thread_handle:
                            kernel32.ResumeThread(thread_handle)
                            kernel32.CloseHandle(thread_handle)
                    if not kernel32.Thread32Next(snapshot, ctypes.byref(te)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)

        logger.debug("Process threads resumed.")
    except Exception as e:
        logger.debug("Failed to resume process: %s", e)


_global_monitor: ProcessMonitor | None = None


def start_taskmanager_monitor(hide_only: bool = True) -> ProcessMonitor:
    """
    Start the global task manager monitor.
    
    Args:
        hide_only: If True, only hide console window. If False, also suspend process.
    """
    global _global_monitor

    if _global_monitor:
        return _global_monitor

    def on_detected() -> None:
        hide_console_window()
        if not hide_only:
            suspend_current_process()

    def on_cleared() -> None:
        if not hide_only:
            resume_current_process()
        show_console_window()

    _global_monitor = ProcessMonitor(
        on_detected=on_detected,
        on_cleared=on_cleared,
        check_interval=0.3,
    )
    _global_monitor.start()
    return _global_monitor


def stop_taskmanager_monitor() -> None:
    """Stop the global task manager monitor."""
    global _global_monitor
    if _global_monitor:
        _global_monitor.stop()
        _global_monitor = None
