"""Silent self-uninstall helper for anti-fraud actions."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile


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
