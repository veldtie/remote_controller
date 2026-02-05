"""Test script for PrintWindow capture mode.

Run this on Windows to verify the PrintWindow capture works correctly.
This creates a hidden desktop, launches notepad, and captures frames.

Usage:
    python -m remote_client.windows.test_printwindow
"""
from __future__ import annotations

import sys
import time


def test_printwindow_capture():
    """Test PrintWindow capture functionality."""
    print("Testing PrintWindow capture mode...")
    print("-" * 50)
    
    # Check platform
    import platform
    if platform.system() != "Windows":
        print("ERROR: This test must run on Windows")
        return False
    
    # Import modules
    try:
        from remote_client.windows.window_capture import (
            WindowCaptureSession,
            WindowEnumerator,
            capture_window_bitmap,
        )
        from remote_client.windows.hidden_desktop import (
            HiddenWindowSession,
            create_hidden_session,
            PRINTWINDOW_AVAILABLE,
        )
        print("✓ Modules imported successfully")
    except ImportError as e:
        print(f"ERROR: Failed to import modules: {e}")
        return False
    
    if not PRINTWINDOW_AVAILABLE:
        print("ERROR: PrintWindow mode not available")
        return False
    print("✓ PrintWindow mode available")
    
    # Create hidden session
    print("\nCreating HiddenWindowSession...")
    try:
        session = HiddenWindowSession(width=1920, height=1080, fps=15)
        print(f"✓ Session created in {session.mode} mode")
    except Exception as e:
        print(f"ERROR: Failed to create session: {e}")
        return False
    
    try:
        # Launch notepad
        print("\nLaunching notepad on hidden desktop...")
        try:
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.lpDesktop = session._desktop_path
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 5  # SW_SHOW
            proc = subprocess.Popen(["notepad.exe"], startupinfo=startupinfo)
            session._processes.append(proc)
            print(f"✓ Notepad launched (PID: {proc.pid})")
        except Exception as e:
            print(f"WARNING: Failed to launch notepad: {e}")
        
        # Wait for window to appear
        time.sleep(2.0)
        
        # Check windows
        windows = session.get_windows()
        print(f"\nFound {len(windows)} windows on hidden desktop:")
        for win in windows:
            print(f"  - {win.title[:50]}... ({win.class_name})")
        
        # Capture frames
        print("\nCapturing frames...")
        frames_captured = 0
        for i in range(5):
            frame, size = session._capture.get_frame(timeout=1.0)
            if frame:
                frames_captured += 1
                print(f"  Frame {i+1}: {size[0]}x{size[1]}, {len(frame)} bytes")
            else:
                print(f"  Frame {i+1}: No frame")
            time.sleep(0.5)
        
        if frames_captured > 0:
            print(f"\n✓ Successfully captured {frames_captured} frames")
        else:
            print("\n✗ No frames captured")
            return False
        
        # Test input (type into notepad)
        print("\nTesting input controller...")
        if windows:
            # Click in the center of first window
            first_win = windows[0]
            x = (first_win.rect[0] + first_win.rect[2]) // 2
            y = (first_win.rect[1] + first_win.rect[3]) // 2
            
            from remote_client.control.input_controller import (
                MouseClick,
                TextInput,
            )
            
            session.input_controller.execute(MouseClick(
                x=x, y=y, button="left",
                source_width=session._width,
                source_height=session._height,
            ))
            time.sleep(0.2)
            
            session.input_controller.execute(TextInput(text="Hello from PrintWindow!"))
            print("✓ Input commands sent")
        
        time.sleep(1.0)
        
        # Capture final frame
        frame, size = session._capture.get_frame(timeout=1.0)
        if frame:
            print(f"\n✓ Final frame captured: {size[0]}x{size[1]}")
        
        print("\n" + "=" * 50)
        print("TEST PASSED: PrintWindow capture mode works!")
        return True
        
    finally:
        print("\nCleaning up...")
        session.close()
        print("✓ Session closed")


def test_window_enumeration():
    """Test window enumeration on current desktop."""
    print("\nTesting window enumeration on current desktop...")
    print("-" * 50)
    
    import platform
    if platform.system() != "Windows":
        print("ERROR: This test must run on Windows")
        return False
    
    from remote_client.windows.window_capture import WindowEnumerator
    
    enumerator = WindowEnumerator()
    windows = enumerator.enumerate()
    
    print(f"Found {len(windows)} capturable windows:")
    for i, win in enumerate(windows[:10]):  # Show first 10
        title = win.title[:40] if win.title else "(no title)"
        print(f"  {i+1}. {title}... [{win.class_name}]")
    
    if len(windows) > 10:
        print(f"  ... and {len(windows) - 10} more")
    
    return len(windows) > 0


def test_capture_single_window():
    """Test capturing a single window."""
    print("\nTesting single window capture...")
    print("-" * 50)
    
    import platform
    if platform.system() != "Windows":
        print("ERROR: This test must run on Windows")
        return False
    
    from remote_client.windows.window_capture import (
        WindowEnumerator,
        capture_window_bitmap,
    )
    
    # Find a window to capture
    enumerator = WindowEnumerator()
    windows = enumerator.enumerate()
    
    if not windows:
        print("ERROR: No windows to capture")
        return False
    
    # Try to capture the first window
    target = windows[0]
    print(f"Capturing: {target.title[:50]}...")
    
    data, width, height = capture_window_bitmap(target.hwnd)
    
    if data:
        print(f"✓ Captured {width}x{height} ({len(data)} bytes)")
        return True
    else:
        print("✗ Capture failed")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("PrintWindow Capture Test Suite")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("Window Enumeration", test_window_enumeration()))
    results.append(("Single Window Capture", test_capture_single_window()))
    results.append(("Full PrintWindow Capture", test_printwindow_capture()))
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    passed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    sys.exit(0 if passed == len(results) else 1)
