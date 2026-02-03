from __future__ import annotations

import os
import shutil
import subprocess








    creationflags = 0
    startupinfo = None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    subprocess.Popen(
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
