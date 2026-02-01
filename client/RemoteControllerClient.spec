# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_root = Path(__file__).resolve().parent
entrypoint = project_root / "client.py"

# Add custom config files to datas if needed, for example:
# datas += [(str(project_root / "remote_client" / "rc_server.json"), "remote_client")]

datas = []
binaries = []
hiddenimports = [
    "cryptography",
    "win32crypt",
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
]

for package in ("av", "aiortc", "sounddevice", "mss", "numpy", "pynput"):
    tmp_datas, tmp_binaries, tmp_hidden = collect_all(package)
    datas += tmp_datas
    binaries += tmp_binaries
    hiddenimports += tmp_hidden


a = Analysis(
    [str(entrypoint)],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RemoteControllerClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
