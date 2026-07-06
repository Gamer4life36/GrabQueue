# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['D:\\SAVE THESE\\GrabQueue\\main.py'],
    pathex=['D:\\SAVE THESE\\GrabQueue'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # the engines\ folder is downloaded at runtime next to the exe — never bundled
    excludes=['cv2', 'numpy', 'PIL', 'selenium'],
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
    name='GrabQueue',
    icon='D:\\SAVE THESE\\GrabQueue\\grabqueue.ico',
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
