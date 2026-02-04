# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['G:\\git\\remote_controller\\operator_desktop\\entrypoint.py'],
    pathex=[],
    binaries=[],
    datas=[('G:\\git\\remote_controller\\operator_desktop\\assets', 'operator_desktop\\\\assets'), ('G:\\git\\remote_controller\\operator_desktop\\..\\\\operator', 'operator')],
    hiddenimports=['PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebChannel'],
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
    name='RemDeskOperator',
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
    icon=['G:\\git\\remote_controller\\operator_desktop\\assets\\icons\\icon.ico'],
)
