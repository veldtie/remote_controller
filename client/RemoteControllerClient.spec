# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\makab\\AppData\\Local\\Temp\\rc_build_rbq2b2fs\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Users\\makab\\AppData\\Local\\Temp\\rc_build_rbq2b2fs\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Users\\makab\\AppData\\Local\\Temp\\rc_build_rbq2b2fs\\remote_client\\rc_server.json', 'remote_client'), ('C:\\Users\\makab\\AppData\\Local\\Temp\\rc_build_rbq2b2fs\\remote_client\\rc_activity.env', 'remote_client')]
binaries = []
hiddenimports = ['win32crypt', 'cryptography', 'pynput', 'pynput.mouse', 'pynput.keyboard', 'remote_client.config', 'remote_client.apps', 'remote_client.apps.launcher', 'remote_client.windows.hidden_desktop', 'remote_client.proxy.socks5_server']
hiddenimports += collect_submodules('remote_client')
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
    ['C:\\Users\\makab\\PycharmProjects\\ремоте контроллер\\client\\client.py'],
    pathex=['C:\\Users\\makab\\PycharmProjects\\ремоте контроллер\\client'],
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
