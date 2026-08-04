# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\tokengotchi\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['pygame', 'pygame.mixer', 'pygame.font', 'pygame.image', 'pygame.display', 'watchdog', 'watchdog.observers', 'watchdog.observers.polling', 'watchdog.events', 'pydantic', 'pydantic_core'],
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
    name='TokenGotchi_debug',
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
