# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

base_dir = Path(__file__).resolve().parent  # .../client
remote_pkg_dir = base_dir / "remote_client"

datas: list[tuple[str, str]] = []
for filename in ("rc_team_id.txt", "rc_antifraud.json", "rc_server.json", "rc_activity.env"):
    path = remote_pkg_dir / filename
    if path.exists():
        datas.append((str(path), "remote_client"))

binaries: list[tuple[str, str, str]] = []
hiddenimports = [
    "win32crypt",
    "cryptography",
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
    "remote_client.config",
]
hiddenimports += collect_submodules("remote_client")

for module in ("pynput", "av", "aiortc", "sounddevice", "mss", "numpy"):
    tmp_ret = collect_all(module)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ["client.py"],
    pathex=[str(base_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy.f2py.tests", "pytest"],
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

