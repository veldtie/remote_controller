# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\USER\\AppData\\Local\\Temp\\rc_build_ugb8sgk1\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Users\\USER\\AppData\\Local\\Temp\\rc_build_ugb8sgk1\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Users\\USER\\AppData\\Local\\Temp\\rc_build_ugb8sgk1\\remote_client\\rc_server.json', 'remote_client')]
binaries = []
hiddenimports = ['win32crypt', 'cryptography', 'pynput', 'pynput.mouse', 'pynput.keyboard']
tmp_ret = collect_all('pynput')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\USER\\remote_controller\\client\\client.py'],
    pathex=[],
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
