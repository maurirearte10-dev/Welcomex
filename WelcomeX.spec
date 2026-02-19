# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Incluir assets, config y videos demo dentro del .exe
# NO incluir data (se crea junto al .exe para la base de datos)
datas = [
    ('assets', 'assets'),
    ('config', 'config'),
    ('locales', 'locales'),
    ('demo_videos', 'demo_videos'),
    ('PLANTILLA_INVITADOS_WELCOMEX.xlsx', '.'),  # Plantilla Excel bundleada
]
binaries = []
hiddenimports = ['PIL._tkinter_finder', 'jwt']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# pynput completo para que el lector de QR funcione en el .exe
tmp_ret2 = collect_all('pynput')
datas += tmp_ret2[0]; binaries += tmp_ret2[1]; hiddenimports += tmp_ret2[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='WelcomeX',
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
    icon=['assets\\icon.ico'],
)
