"""Genera packaging/windows/icon.ico desde el ícono programático de la app.

Se corre una vez antes del build de Windows:
    python packaging/make_icon.py
(No se versiona ningún binario: el .ico se regenera en cada build.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from transcriptor.gui.app import _make_icon  # noqa: E402


def main():
    app = QGuiApplication([])  # noqa: F841 — Qt necesita una app para pintar
    out = Path(__file__).parent / "windows" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)

    icon = _make_icon()
    # Un .ico moderno puede contener PNGs; guardamos varios tamaños.
    pngs = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = icon.pixmap(size, size)
        buf = QBuffer()
        buf.open(QBuffer.WriteOnly)
        pm.save(buf, "PNG")
        pngs.append((size, bytes(buf.data())))
        buf.close()

    # Contenedor ICO con entradas PNG (soportado desde Windows Vista).
    import struct

    header = struct.pack("<HHH", 0, 1, len(pngs))
    entries = b""
    blobs = b""
    offset = len(header) + 16 * len(pngs)
    for size, data in pngs:
        s = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", s, s, 0, 0, 1, 32, len(data), offset
        )
        blobs += data
        offset += len(data)

    out.write_bytes(header + entries + blobs)
    print(f"OK → {out}")


if __name__ == "__main__":
    main()
