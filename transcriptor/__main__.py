"""Entrada del paquete: `python -m transcriptor` abre la GUI; `--cli` corre
una pasada única estilo cron (sin dependencia de Qt)."""

import sys


def main():
    if "--cli" in sys.argv:
        from .cli import main as run
    else:
        from .gui.app import main as run
    sys.exit(run() or 0)


if __name__ == "__main__":
    main()
