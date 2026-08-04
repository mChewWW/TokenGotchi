# -*- mode: python ; coding: utf-8 -*-
# TokenGotchi PyInstaller spec file

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Collect pygame data files (SDL DLLs, fonts, etc.)
pygame_datas = collect_data_files('pygame')

a = Analysis(
    ['src/tokengotchi/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        *pygame_datas,
    ],
    hiddenimports=[
        'pygame',
        'pygame.mixer',
        'pygame.font',
        'pygame.image',
        'pygame.display',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'pydantic',
        'pydantic_core',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='TokenGotchi',
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
    onefile=True,
    icon=None,
)
