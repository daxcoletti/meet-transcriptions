"""Modo CLI de una sola pasada, pensado para cron / Programador de tareas.

Replica el comportamiento histórico: cada instancia toma UN archivo pendiente,
lo procesa y termina. Los locks entre instancias usan `filelock`
(multiplataforma) en vez de fcntl.
"""

import hashlib
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout

from . import config, engine
from .engine import GREEN, YELLOW, RESET, log

LOCK_DIR = Path(tempfile.gettempdir()) / "transcripcion_locks"


def _lock_path(file_path):
    """Hash del path absoluto para evitar colisiones por nombres con caracteres raros."""
    h = hashlib.sha1(str(file_path.resolve()).encode()).hexdigest()[:16]
    return LOCK_DIR / f"{h}.lock"


def main():
    cfg = config.load()
    cfg.ensure_dirs()
    engine.configure(cfg)
    LOCK_DIR.mkdir(exist_ok=True)

    if not cfg.log_file.exists():
        cfg.log_file.touch()

    to_process = engine.pending_files()
    if not to_process:
        log(f"{GREEN}Sin archivos nuevos.{RESET}")
        return 0

    worked = False
    for f in to_process:
        # Re-chequear: otro proceso pudo haber terminado y movido el archivo a procesados/
        if not f.exists():
            continue
        lock = FileLock(_lock_path(f))
        try:
            lock.acquire(timeout=0)
        except Timeout:
            # Otra instancia ya está procesando este archivo: pasar al siguiente
            log(
                f"{YELLOW}⏭  {f.name}: ocupado por otra instancia, "
                f"paso al siguiente.{RESET}"
            )
            continue
        try:
            worked = True
            engine.run_one(f)
        finally:
            lock.release()
        # Solo procesamos UN archivo por instancia: si esta instancia tomó f,
        # otras instancias paralelas pueden estar trabajando con f2, f3, etc.
        break

    if not worked:
        log(
            f"{GREEN}Todos los archivos pendientes están siendo procesados "
            f"por otras instancias.{RESET}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
