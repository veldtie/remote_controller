# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\ChalkBro\\Documents\\GitHub\\remote_controller\\client\\remote_client\\main.py'],
    pathex=[],
    binaries=[],
<<<<<<< HEAD
    datas=[('C:\\Temp\\rc_build_1x_apflw\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Temp\\rc_build_1x_apflw\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Temp\\rc_build_1x_apflw\\remote_client\\rc_server.json', 'remote_client')],
=======
    datas=[('C:\\Temp\\rc_build_ie6yv4yv\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Temp\\rc_build_ie6yv4yv\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Temp\\rc_build_ie6yv4yv\\remote_client\\rc_server.json', 'remote_client')],
>>>>>>> 7f01b70b8325008751faa908a2cbeb8d4bd2b078
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
