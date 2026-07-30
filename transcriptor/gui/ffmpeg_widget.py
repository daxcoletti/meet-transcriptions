"""Widget de estado de ffmpeg con descarga integrada (wizard y Configuración)."""

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import ffmpeg_utils


class _Downloader(QThread):
    progress = Signal(int, int)  # bytes descargados, total (0 = desconocido)
    ok = Signal(str)             # ruta al binario
    failed = Signal(str)         # mensaje de error

    def run(self):
        try:
            path = ffmpeg_utils.download_ffmpeg(
                progress_cb=lambda done, total: self.progress.emit(done, total)
            )
            self.ok.emit(path)
        except Exception as e:
            self.failed.emit(str(e))


class FFmpegStatusWidget(QWidget):
    """Muestra si hay ffmpeg utilizable y permite descargarlo si falta."""

    status_changed = Signal(bool)  # True si hay ffmpeg disponible

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.found_path = None
        self._downloader = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: gray;")
        layout.addWidget(self.hint_label)

        buttons = QHBoxLayout()
        self.download_btn = QPushButton("⬇ Descargar ffmpeg automáticamente")
        self.download_btn.clicked.connect(self._start_download)
        self.recheck_btn = QPushButton("Volver a comprobar")
        self.recheck_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.download_btn)
        buttons.addWidget(self.recheck_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.bar = QProgressBar()
        self.bar.setVisible(False)
        layout.addWidget(self.bar)

        self.refresh()

    def refresh(self):
        self.found_path = ffmpeg_utils.find_ffmpeg(self.cfg)
        if self.found_path:
            self.status_label.setText(
                f'<span style="color:green">✔ ffmpeg encontrado:</span> '
                f"<code>{self.found_path}</code>"
            )
            self.hint_label.setText("")
            self.download_btn.setVisible(False)
        else:
            self.status_label.setText(
                '<span style="color:red">✘ No se encontró ffmpeg.</span> '
                "La aplicación lo necesita para extraer y segmentar el audio."
            )
            if os.name == "nt":
                hint = (
                    "Podés descargarlo automáticamente con el botón de abajo "
                    "(build oficial de gyan.dev, ~90 MB), o instalarlo vos "
                    "mismo y volver a comprobar."
                )
            else:
                hint = (
                    "Instalalo con tu gestor de paquetes (p.ej. "
                    "<code>sudo apt install ffmpeg</code>) y tocá "
                    "«Volver a comprobar», o usá la descarga automática "
                    "(build estático de johnvansickle.com)."
                )
            self.hint_label.setText(hint)
            self.download_btn.setVisible(ffmpeg_utils.download_url() is not None)
        self.status_changed.emit(bool(self.found_path))

    def _start_download(self):
        self.download_btn.setEnabled(False)
        self.recheck_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)  # indeterminado hasta conocer el total

        self._downloader = _Downloader(self)
        self._downloader.progress.connect(self._on_progress)
        self._downloader.ok.connect(self._on_ok)
        self._downloader.failed.connect(self._on_failed)
        self._downloader.start()

    def _on_progress(self, done, total):
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(done)

    def _on_ok(self, path):
        self.bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.recheck_btn.setEnabled(True)
        self.refresh()

    def _on_failed(self, msg):
        self.bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.recheck_btn.setEnabled(True)
        self.status_label.setText(
            f'<span style="color:red">✘ La descarga falló:</span> {msg}'
        )
