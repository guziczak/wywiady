# -*- mode: python ; coding: utf-8 -*-

import os
import sys

tcl_root = os.path.join(sys.base_prefix, 'tcl')
tcl_dir = os.path.join(tcl_root, 'tcl8.6')
tk_dir = os.path.join(tcl_root, 'tk8.6')
datas = []
if os.path.isdir(tcl_dir):
    datas.append((tcl_dir, 'tcl/tcl8.6'))
if os.path.isdir(tk_dir):
    datas.append((tk_dir, 'tcl/tk8.6'))

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
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
    a.binaries,
    a.datas,
    [],
    name='AsystentSetup',
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
    icon=['extension\\icon.ico'],
)
