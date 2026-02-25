# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Enclave Vault desktop application.

Build commands:
    # Development build (console visible for debugging)
    pyinstaller enclave.spec

    # Production build
    pyinstaller enclave.spec --clean

Platform-specific outputs:
    - macOS: dist/Enclave.app
    - Windows: dist/Enclave.exe
    - Linux: dist/Enclave (AppImage recommended for distribution)
"""

import sys
import os
from pathlib import Path

# Detect platform
is_macos = sys.platform == 'darwin'
is_windows = sys.platform == 'win32'
is_linux = sys.platform.startswith('linux')

# Project root
project_root = Path(SPECPATH)

# App metadata
APP_NAME = 'Enclave'
APP_VERSION = '0.1.0'
APP_BUNDLE_ID = 'ai.enclave.vault'

# Entry point
entry_point = str(project_root / 'advanced_vault' / 'gui' / 'vault_app.py')

# Collect all data files
datas = [
    # Include assets if they exist
    (str(project_root / 'assets'), 'assets') if (project_root / 'assets').exists() else None,
    # Include any embedded models or resources
]
datas = [d for d in datas if d is not None]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # Flet
    'flet',
    'flet_core',
    'flet_runtime',
    # Cryptography
    'cryptography',
    'cryptography.hazmat.primitives.ciphers.aead',
    # Database
    'sqlite3',
    'sqlalchemy',
    'sqlalchemy.dialects.sqlite',
    # ML/Embeddings (optional - comment out to reduce size)
    'sentence_transformers',
    'transformers',
    'torch',
    'numpy',
    # MCP
    'mcp',
    'pydantic',
    # HTTP
    'httpx',
    'requests',
    # PDF
    'pypdf',
]

# Exclude packages to reduce size (uncomment as needed)
excludes = [
    # 'torch',  # Exclude if not using local inference
    # 'transformers',
    'tkinter',
    'matplotlib',
    'PIL',
]

# Analysis
a = Analysis(
    [entry_point],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# Remove unnecessary files
a.binaries = [b for b in a.binaries if not b[0].startswith('libQt5')]  # Remove unused Qt

pyz = PYZ(a.pure)

# Platform-specific executable configuration
if is_macos:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # No terminal window
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,  # Universal binary
        codesign_identity=None,  # Set for notarization
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )

    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=str(project_root / 'assets' / 'icon.icns') if (project_root / 'assets' / 'icon.icns').exists() else None,
        bundle_identifier=APP_BUNDLE_ID,
        version=APP_VERSION,
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': 'Enclave Vault',
            'CFBundleVersion': APP_VERSION,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleIdentifier': APP_BUNDLE_ID,
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15.0',
            'NSAppleEventsUsageDescription': 'Enclave needs to communicate with other apps.',
            'NSDocumentsFolderUsageDescription': 'Enclave stores your encrypted vault here.',
        },
    )

elif is_windows:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,  # No console window
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(project_root / 'assets' / 'icon.ico') if (project_root / 'assets' / 'icon.ico').exists() else None,
        version_file=None,  # Can add version info
    )

else:  # Linux
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
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
