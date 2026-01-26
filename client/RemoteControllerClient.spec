# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\abdul\\PycharmProjects\\remote_controller\\client\\client.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\abdul\\AppData\\Local\\Temp\\rc_build_j85moppc\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Users\\abdul\\AppData\\Local\\Temp\\rc_build_j85moppc\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Users\\abdul\\AppData\\Local\\Temp\\rc_build_j85moppc\\remote_client\\rc_server.json', 'remote_client')],
    hiddenimports=[],
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
