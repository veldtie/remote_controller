"""Windows-specific helpers for the remote client."""
from remote_client.windows.hidden_desktop import (
    HiddenDesktopSession,
    HiddenWindowSession,
    create_hidden_session,
    PRINTWINDOW_AVAILABLE,
    VIRTUAL_DISPLAY_AVAILABLE,
)
from remote_client.windows.window_capture import (
    WindowCaptureSession,
    WindowInputController,
    WindowCompositor,
    WindowEnumerator,
    WindowInfo,
    CapturedWindow,
    capture_window_bitmap,
)

__all__ = [
    "HiddenDesktopSession",
    "HiddenWindowSession",
    "create_hidden_session",
    "PRINTWINDOW_AVAILABLE",
    "VIRTUAL_DISPLAY_AVAILABLE",
    "WindowCaptureSession",
    "WindowInputController",
    "WindowCompositor",
    "WindowEnumerator",
    "WindowInfo",
    "CapturedWindow",
    "capture_window_bitmap",
]
