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

# Recurso de versión de Windows (generado por packaging/make_version_info.py)
version_path = os.path.join(SPECPATH, "windows", "version_info.txt")
version_file = version_path if os.path.exists(version_path) else None

# pynput elige su backend con imports dinámicos: hay que declararlos.
import sys as _sys

if _sys.platform == "win32":
    _pynput_hidden = ["pynput.keyboard._win32", "pynput.mouse._win32"]
else:
    _pynput_hidden = ["pynput.keyboard._xorg", "pynput.mouse._xorg"]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=_pynput_hidden,
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
    version=version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MeetTranscriptions",
)
