#!/usr/bin/env python3
"""Wrapper de compatibilidad: el cron existente invoca este archivo.

Toda la lógica vive ahora en el paquete `transcriptor/`. Este script solo
delega en el modo CLI (una pasada: toma un archivo pendiente, lo procesa y
termina), que se comporta igual que el viejo script monolítico.
"""

from transcriptor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
