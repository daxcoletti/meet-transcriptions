"""Wizard de primera ejecución: bienvenida → ffmpeg → API keys → carpeta → fin.

Se abre solo cuando todavía no existe config.json. Reaparece la lógica de
cada página en el diálogo de Configuración para cambios posteriores.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from .. import autostart, config
from ..config import Config
from .ffmpeg_widget import FFmpegStatusWidget
from .keys_form import KeysForm


class _IntroPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Bienvenido a Meet Transcriptions")
        text = QLabel(
            "Esta aplicación vigila una carpeta de grabaciones (Google Meet, "
            "Zoom, llamadas…) y, por cada audio nuevo, genera automáticamente:"
            "<ul>"
            "<li>la <b>transcripción</b> con identificación de hablantes "
            "(VTT, TXT y JSON), y</li>"
            "<li>una <b>minuta</b> en Markdown con resumen, decisiones y "
            "tareas.</li>"
            "</ul>"
            "Usa los planes <b>gratuitos</b> de varios servicios de "
            "transcripción, rotando entre ellos para esquivar los límites de "
            "cuota. En los próximos pasos vamos a verificar <b>ffmpeg</b>, "
            "cargar tus <b>API keys</b> y elegir la <b>carpeta</b> a vigilar."
        )
        text.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(text)


class _FFmpegPage(QWizardPage):
    def __init__(self, cfg):
        super().__init__()
        self.setTitle("Paso 1 · ffmpeg")
        self.setSubTitle(
            "ffmpeg es un programa externo (gratuito y de código abierto) que "
            "la aplicación usa para extraer y segmentar el audio."
        )
        self.widget = FFmpegStatusWidget(cfg)
        self.widget.status_changed.connect(lambda _: self.completeChanged.emit())

        self.skip = QCheckBox("Continuar sin ffmpeg (lo instalo yo más tarde)")
        self.skip.toggled.connect(lambda _: self.completeChanged.emit())

        layout = QVBoxLayout(self)
        layout.addWidget(self.widget)
        layout.addStretch(1)
        layout.addWidget(self.skip)

    def initializePage(self):
        self.widget.refresh()

    def isComplete(self):
        return bool(self.widget.found_path) or self.skip.isChecked()


class _KeysPage(QWizardPage):
    def __init__(self, initial_keys):
        super().__init__()
        self.setTitle("Paso 2 · API keys")
        self.setSubTitle(
            "Registrate gratis en los servicios que quieras (el nombre de cada "
            "uno es un enlace) y pegá acá sus API keys. Con UNA key de "
            "transcripción alcanza; cuantas más cargues, más cuota gratuita "
            "total y mejor tolerancia a fallos."
        )
        self.form = KeysForm()
        self.form.set_keys(initial_keys)
        self.form.changed.connect(self.completeChanged.emit)

        scroll = QScrollArea()
        scroll.setWidget(self.form)
        scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

    def isComplete(self):
        return self.form.has_transcription_key()


class _FolderPage(QWizardPage):
    def __init__(self, default_dir):
        super().__init__()
        self.setTitle("Paso 3 · Carpeta de grabaciones")
        self.setSubTitle(
            "Todo audio o video que aparezca en esta carpeta se transcribe "
            "automáticamente. Los resultados quedan en subcarpetas "
            "(transcriptions/, Minutas/) y el original se mueve a procesados/."
        )
        self.edit = QLineEdit(str(default_dir))
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse)

        row = QHBoxLayout()
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addStretch(1)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Elegí la carpeta de grabaciones", self.edit.text()
        )
        if d:
            self.edit.setText(d)

    def isComplete(self):
        return bool(self.edit.text().strip())


class _FinalPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("¡Listo!")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.autostart = QCheckBox("Iniciar Meet Transcriptions al encender el equipo")
        self.autostart.setChecked(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addStretch(1)
        layout.addWidget(self.autostart)

    def initializePage(self):
        wiz = self.wizard()
        n_keys = len(wiz.keys_page.form.get_keys())
        folder = wiz.folder_page.edit.text().strip()
        ffmpeg_ok = bool(wiz.ffmpeg_page.widget.found_path)
        lines = [
            f"• Carpeta vigilada: <b>{folder}</b>",
            f"• API keys configuradas: <b>{n_keys}</b>",
            "• ffmpeg: <b>disponible ✔</b>" if ffmpeg_ok
            else '• ffmpeg: <b style="color:red">pendiente de instalar ✘</b>',
            "",
            "Al finalizar, la aplicación queda en la <b>bandeja del sistema</b> "
            "(junto al reloj) vigilando la carpeta. Podés cambiar todo esto "
            "después desde el menú «Configuración».",
        ]
        self.summary.setText("<br>".join(lines))


class SetupWizard(QWizard):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meet Transcriptions — Configuración inicial")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(760, 560)

        self.ffmpeg_page = _FFmpegPage(cfg)
        self.keys_page = _KeysPage(cfg.api_keys)
        self.folder_page = _FolderPage(cfg.audios_dir)
        self.final_page = _FinalPage()

        self.addPage(_IntroPage())
        self.addPage(self.ffmpeg_page)
        self.addPage(self.keys_page)
        self.addPage(self.folder_page)
        self.addPage(self.final_page)

        self._base = cfg

    def accept(self):
        data = dict(self._base.data)
        data["api_keys"] = self.keys_page.form.get_keys()
        data["audios_dir"] = str(Path(self.folder_page.edit.text().strip()).expanduser())
        cfg = Config(data)
        cfg.save()
        cfg.ensure_dirs()

        try:
            if self.final_page.autostart.isChecked():
                autostart.enable()
            else:
                autostart.disable()
        except OSError:
            pass  # sin autostart no es fatal

        super().accept()


def run_wizard(parent=None):
    """Ejecuta el wizard. Devuelve la Config nueva, o None si se canceló."""
    wiz = SetupWizard(config.load(), parent)
    if wiz.exec() == QWizard.Accepted:
        return config.load()
    return None
