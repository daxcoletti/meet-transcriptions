"""Vigilancia de la carpeta de audios con eventos nativos del sistema.

Usa `watchdog`, que por debajo emplea inotify en Linux y
ReadDirectoryChangesW en Windows: cero polling mientras no pasa nada.

Un único hilo worker procesa los archivos de a uno (no hacen falta locks
entre instancias como en el modo cron: acá hay un solo proceso).
"""

import queue
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import engine
from .config import VALID_EXTENSIONS

_STOP = object()


class _NewAudioHandler(FileSystemEventHandler):
    def __init__(self, submit):
        self._submit = submit

    def on_created(self, event):
        if not event.is_directory:
            self._submit(Path(event.src_path))

    def on_moved(self, event):
        # Muchas apps graban a un nombre temporal y renombran al terminar.
        if not event.is_directory:
            self._submit(Path(event.dest_path))


class AudioWatcher:
    """Observa la carpeta de audios y procesa cada archivo nuevo.

    Callbacks (se invocan desde el hilo worker — la GUI debe puentearlos
    con señales Qt):
      on_file_done(nombre, ok): terminó de procesar un archivo.
    """

    def __init__(self, cfg, on_file_done=None):
        self.cfg = cfg
        self.on_file_done = on_file_done
        self._queue = queue.Queue()
        self._queued = set()          # paths encolados o en proceso
        self._queued_lock = threading.Lock()
        self._paused = threading.Event()
        self._observer = None
        self._worker = None

    # --- API pública ---
    def start(self):
        self.cfg.ensure_dirs()
        self._worker = threading.Thread(
            target=self._work_loop, name="transcriptor-worker", daemon=True
        )
        self._worker.start()

        handler = _NewAudioHandler(self._submit)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.cfg.audios_dir), recursive=False)
        self._observer.start()

        # Barrido inicial: archivos que llegaron mientras la app estaba cerrada.
        for f in engine.pending_files():
            self._submit(f)

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._worker:
            self._queue.put(_STOP)

    def pause(self):
        self._paused.set()
        engine.log("⏸  Procesamiento en pausa.")

    def resume(self):
        self._paused.clear()
        engine.log("▶️  Procesamiento reanudado.")

    @property
    def paused(self):
        return self._paused.is_set()

    # --- Internos ---
    def _submit(self, path):
        if path.suffix.lower() not in VALID_EXTENSIONS:
            return
        with self._queued_lock:
            if path in self._queued:
                return
            self._queued.add(path)
        self._queue.put(path)

    def _work_loop(self):
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            try:
                self._process(item)
            finally:
                with self._queued_lock:
                    self._queued.discard(item)

    def _process(self, path):
        while self._paused.is_set():
            time.sleep(1)

        if not self._wait_until_stable(path):
            return  # desapareció mientras se copiaba

        if not path.exists() or path.name in engine.load_processed_set():
            return

        ok = engine.run_one(path)
        if self.on_file_done:
            try:
                self.on_file_done(path.name, ok)
            except Exception:
                pass

    @staticmethod
    def _wait_until_stable(path, interval=2.0, checks=3, timeout=3600):
        """Espera a que el archivo termine de escribirse (tamaño estable).

        Las grabaciones suelen copiarse/descargarse de a poco; procesarlas a
        medio escribir corrompe la transcripción y quema cuota gratuita.
        """
        deadline = time.monotonic() + timeout
        last = -1
        stable = 0
        while stable < checks:
            if time.monotonic() > deadline:
                return False
            try:
                size = path.stat().st_size
            except OSError:
                return False
            if size == last and size > 0:
                stable += 1
            else:
                stable = 0
                last = size
            time.sleep(interval)
        return True
