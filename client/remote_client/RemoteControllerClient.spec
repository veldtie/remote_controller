# -*- mode: python ; coding: utf-8 -*-
<<<<<<< HEAD
from PyInstaller.utils.hooks import collect_all
=======
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH is provided by PyInstaller - path to the .spec file
BASE_DIR = Path(SPECPATH).resolve()
PROJECT_DIR = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

datas = []
for name in ("rc_team_id.txt", "rc_antifraud.json", "rc_server.json"):
    candidate = BASE_DIR / name
    if candidate.exists():
        datas.append((str(candidate), "remote_client"))

# =============================================================================
# VIRTUAL DISPLAY DRIVER - добавление драйвера в сборку
# =============================================================================
# Папка с драйвером (после запуска download_driver.py)
VDD_DRIVER_DIR = BASE_DIR / "drivers" / "vdd"
if VDD_DRIVER_DIR.exists():
    # Добавляем все файлы драйвера в сборку
    for ext in ["*.inf", "*.sys", "*.cat", "*.dll", "*.exe"]:
        for f in VDD_DRIVER_DIR.glob(ext):
            datas.append((str(f), "drivers/vdd"))
    print(f"[VDD] Driver files added from: {VDD_DRIVER_DIR}")
else:
    print(f"[VDD] WARNING: Driver not found at {VDD_DRIVER_DIR}")
    print(f"[VDD] Run: python download_driver.py in windows/drivers/")
# =============================================================================
>>>>>>> efddd4bd25860f3b35a15bed34bae19f641a9d27

datas = [('C:\\Temp\\rc_build_fnvz43dc\\remote_client\\rc_team_id.txt', 'remote_client'), ('C:\\Temp\\rc_build_fnvz43dc\\remote_client\\rc_antifraud.json', 'remote_client'), ('C:\\Temp\\rc_build_fnvz43dc\\remote_client\\rc_server.json', 'remote_client')]
binaries = []
hiddenimports = ['win32crypt', 'cryptography', 'pynput', 'pynput.mouse', 'pynput.keyboard', 'remote_client.apps', 'remote_client.apps.launcher', 'remote_client.windows.hidden_desktop']
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
    ['C:\\Users\\Versus Cyber Arena\\remote_controller\\client\\remote_client\\main.py'],
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
