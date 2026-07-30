"""Genera packaging/windows/version_info.txt para PyInstaller.

Es el recurso de versión de Windows: lo que se ve en Propiedades → Detalles
del exe (producto, versión, compañía). Además de prolijidad, los servicios
de firma (SignPath) esperan binarios con metadatos consistentes.

Se corre antes de pyinstaller:  python packaging/make_version_info.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transcriptor import __version__  # noqa: E402

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple},
    prodvers={tuple},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'TRANS-IT Foundation'),
        StringStruct('FileDescription', 'Meet Transcriptions — automatic meeting transcription and minutes'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'MeetTranscriptions'),
        StringStruct('LegalCopyright', 'TRANS-IT Foundation. Licensed under GPL-3.0-or-later.'),
        StringStruct('OriginalFilename', 'MeetTranscriptions.exe'),
        StringStruct('ProductName', 'Meet Transcriptions'),
        StringStruct('ProductVersion', '{version}'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def main():
    parts = [int(p) for p in __version__.split(".")]
    while len(parts) < 4:
        parts.append(0)
    out = Path(__file__).parent / "windows" / "version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        TEMPLATE.format(tuple=tuple(parts[:4]), version=__version__),
        encoding="utf-8",
    )
    print(f"OK -> {out} ({__version__})")


if __name__ == "__main__":
    main()
