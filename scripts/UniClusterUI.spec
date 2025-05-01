# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['my_hpc_app/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('my_hpc_app/resources', 'resources'),
        ('my_hpc_app/modules', 'modules'),
        ('my_hpc_app/ui', 'ui'),
        ('requirements.txt', '.'),
        ('LICENSE', '.'),
        ('NOTICE.txt', '.')
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
    name='HpcManagementSystem',
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
    icon='my_hpc_app/resources/icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HpcManagementSystem',
)

# macOS specific
app = BUNDLE(
    coll,
    name='HpcManagementSystem.app',
    icon='my_hpc_app/resources/icon.icns',
    bundle_identifier='com.hpc.management',
    info_plist={
        'CFBundleShortVersionString': '0.0.1',
        'CFBundleVersion': '0.0.1',
        'NSHumanReadableCopyright': 'Copyright © 2024 Song Liangyu and contributors. All rights reserved.',
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
    },
)
