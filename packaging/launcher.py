"""Punto de entrada para PyInstaller.

GUI por defecto; con `--cli` corre una pasada única estilo cron (útil para
el Programador de tareas de Windows o cron en Linux con la app empaquetada).
"""

from transcriptor.__main__ import main

if __name__ == "__main__":
    main()
