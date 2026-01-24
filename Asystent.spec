# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect NiceGUI data files
nicegui_datas = collect_data_files('nicegui')

# Project data files
datas = nicegui_datas + [
    ('app_ui', 'app_ui'),
    ('core', 'core'),
    ('templates', 'templates'),
    ('extension', 'extension'),
]

# Add assets if exists
if os.path.isdir('assets'):
    datas.append(('assets', 'assets'))

# Add data folder if exists
if os.path.isdir('data'):
    datas.append(('data', 'data'))

# Hidden imports for NiceGUI and dependencies
hiddenimports = [
    'nicegui',
    'nicegui.ui',
    'fastapi',
    'uvicorn',
    'starlette',
    'httptools',
    'uvloop',
    'websockets',
    'aiofiles',
    'httpx',
    'markdown2',
    'pygments',
    'watchfiles',
    'multipart',
    'python_multipart',
    'itsdangerous',
    'orjson',
    'engineio',
    'socketio',
    'bidict',
    # Audio/ML
    'sounddevice',
    'numpy',
    'scipy',
    'torch',
    'torchaudio',
    'transformers',
    'faster_whisper',
    'ctranslate2',
    # Other
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'anthropic',
    'google.generativeai',
    'openai',
]

# Collect all submodules
hiddenimports += collect_submodules('nicegui')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')

a = Analysis(
    ['stomatolog_nicegui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Asystent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # True for debugging, change to False for release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='extension/icon_v3.ico' if os.path.exists('extension/icon_v3.ico') else None,
)
