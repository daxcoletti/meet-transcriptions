"""Genera el ícono PNG (256px) para el paquete .deb.

Uso: python packaging/make_png_icon.py <ruta-salida.png>
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402


def main():
    app = QGuiApplication([])  # noqa: F841 — Qt necesita una app para pintar
    from transcriptor.gui.app import _make_icon

    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    _make_icon().pixmap(256, 256).save(str(out), "PNG")
    print(f"OK -> {out}")


if __name__ == "__main__":
    main()
