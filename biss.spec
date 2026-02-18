# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Bilingual Subtitle Suite (BISS).

Builds a single-file Windows executable:
  - Double-click: launches GUI (no args → gui mode)
  - Terminal: full CLI (python biss.exe merge ...)

Build with:
  pyinstaller biss.spec

Or use the build script:
  python build.py
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Project root
ROOT = os.path.dirname(os.path.abspath(SPEC))

# Collect all project source modules
source_dirs = ['core', 'processors', 'ui', 'utils', 'third_party']
hidden_imports = []
for d in source_dirs:
    dir_path = os.path.join(ROOT, d)
    if os.path.isdir(dir_path):
        for f in os.listdir(dir_path):
            if f.endswith('.py') and f != '__init__.py':
                module_name = f'{d}.{f[:-3]}'
                hidden_imports.append(module_name)

# Add additional hidden imports that PyInstaller might miss
hidden_imports.extend([
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    'charset_normalizer',
    'pysrt',
    'dotenv',
    'requests',
])

# Data files to bundle
datas = []

# Bundle images
images_dir = os.path.join(ROOT, 'images')
if os.path.isdir(images_dir):
    datas.append((images_dir, 'images'))

# Bundle third_party config templates (not the large install directory)
third_party_init = os.path.join(ROOT, 'third_party', '__init__.py')
if os.path.exists(third_party_init):
    datas.append((os.path.join(ROOT, 'third_party', '__init__.py'), 'third_party'))
    datas.append((os.path.join(ROOT, 'third_party', 'pgsrip_wrapper.py'), 'third_party'))

a = Analysis(
    [os.path.join(ROOT, 'biss.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'jupyter',
        'notebook',
        'pytest',
        'black',
        'flake8',
        'mypy',
    ],
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
    a.zipfiles,
    a.datas,
    [],
    name='biss',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console mode: supports both CLI and GUI (Tkinter works in console mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'images', 'biss-logo.png') if os.path.exists(os.path.join(ROOT, 'images', 'biss-logo.png')) else None,
)
