# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller packaging/transcriptor.spec
# Genera dist/MeetTranscriptions/ (modo onedir: arranca rápido y da menos
# falsos positivos de antivirus que onefile).

import os

from PyInstaller.utils.hooks import collect_data_files

# SPECPATH = directorio que contiene este .spec (lo define PyInstaller)
ROOT = os.path.dirname(SPECPATH)

# langdetect necesita sus perfiles de idioma (archivos de datos del paquete).
datas = collect_data_files("langdetect")

icon_path = os.path.join(SPECPATH, "windows", "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="MeetTranscriptions",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MeetTranscriptions",
)
