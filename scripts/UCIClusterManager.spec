# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Get the absolute paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(SPECPATH))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # 项目根目录是scripts的父目录
MAIN_PY = os.path.join(PROJECT_ROOT, 'my_hpc_app', 'main.py')

# Debug info
print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
print(f"MAIN_PY: {MAIN_PY}")
print(f"MAIN_PY exists: {os.path.exists(MAIN_PY)}")
print(f"Current working directory: {os.getcwd()}")
print(f"sys.path: {sys.path}")

# List directory contents to debug
print("Project root contents:")
for item in os.listdir(PROJECT_ROOT):
    print(f"  - {item}")

# 检查my_hpc_app是否存在
if not os.path.exists(os.path.join(PROJECT_ROOT, 'my_hpc_app')):
    print(f"错误: my_hpc_app目录不存在: {os.path.join(PROJECT_ROOT, 'my_hpc_app')}")
    print("当前目录内容:")
    for item in os.listdir(os.getcwd()):
        print(f"  - {item}")
    sys.exit(1)

a = Analysis(
    [MAIN_PY],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'my_hpc_app', 'resources'), 'resources'),
        (os.path.join(PROJECT_ROOT, 'my_hpc_app', 'modules'), 'modules'),
        (os.path.join(PROJECT_ROOT, 'my_hpc_app', 'ui'), 'ui'),
        (os.path.join(PROJECT_ROOT, 'requirements.txt'), '.'),
        (os.path.join(PROJECT_ROOT, 'LICENSE'), '.'),
        (os.path.join(PROJECT_ROOT, 'docs', 'NOTICE.txt'), '.')
    ],
    hiddenimports=[
        'pexpect', 'paramiko', 'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui',
        'json', 'os', 'sys', 'time', 'logging', 'subprocess', 'datetime',
        'cryptography', 'bcrypt', 'pynacl', 'requests', 'packaging', 'packaging.version'
    ],
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
    [],
    exclude_binaries=True,
    name='UCI-ClusterManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'my_hpc_app/resources/icon.ico'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UCI-ClusterManager',
)

# macOS specific
app = BUNDLE(
    coll,
    name='UCI-ClusterManager.app',
    icon=os.path.join(PROJECT_ROOT, 'my_hpc_app/resources/icon.icns'),
    bundle_identifier='edu.uci.clustermanager',
    info_plist={
        'CFBundleShortVersionString': '0.0.1',
        'CFBundleVersion': '0.0.1',
        'NSHumanReadableCopyright': 'Copyright © 2024 Song Liangyu and contributors. All rights reserved.',
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
    },
)
