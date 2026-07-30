"""Diálogo de Configuración: keys, carpeta, idioma de Speechmatics, autostart."""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from .. import autostart
from ..config import Config
from .ffmpeg_widget import FFmpegStatusWidget
from .keys_form import KeysForm

SPEECHMATICS_LANGS = ["en", "es", "pt", "fr", "de", "it"]


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meet Transcriptions — Configuración")
        self.setMinimumSize(780, 640)
        self._base = cfg
        self.result_config = None

        layout = QVBoxLayout(self)

        # --- API keys ---
        keys_box = QGroupBox("API keys (los nombres son enlaces para registrarse)")
        self.keys_form = KeysForm()
        self.keys_form.set_keys(cfg.api_keys)
        scroll = QScrollArea()
        scroll.setWidget(self.keys_form)
        scroll.setWidgetResizable(True)
        kb_layout = QVBoxLayout(keys_box)
        kb_layout.addWidget(scroll)
        layout.addWidget(keys_box, 1)

        # --- Opciones generales ---
        general = QGroupBox("General")
        form = QFormLayout(general)

        self.folder_edit = QLineEdit(str(cfg.audios_dir))
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        form.addRow("Carpeta vigilada:", folder_row)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(SPEECHMATICS_LANGS)
        if cfg.speechmatics_lang in SPEECHMATICS_LANGS:
            self.lang_combo.setCurrentText(cfg.speechmatics_lang)
        self.lang_combo.setToolTip(
            "Speechmatics no detecta idioma automáticamente: transcribe con "
            "un idioma fijo por trabajo."
        )
        form.addRow("Idioma (Speechmatics):", self.lang_combo)

        self.autostart_check = QCheckBox("Iniciar al encender el equipo")
        self.autostart_check.setChecked(autostart.is_enabled())
        form.addRow("", self.autostart_check)

        layout.addWidget(general)

        # --- ffmpeg ---
        ffmpeg_box = QGroupBox("ffmpeg")
        fb_layout = QVBoxLayout(ffmpeg_box)
        fb_layout.addWidget(FFmpegStatusWidget(cfg))
        layout.addWidget(ffmpeg_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Elegí la carpeta de grabaciones", self.folder_edit.text()
        )
        if d:
            self.folder_edit.setText(d)

    def accept(self):
        data = dict(self._base.data)
        data["api_keys"] = self.keys_form.get_keys()
        data["audios_dir"] = str(Path(self.folder_edit.text().strip()).expanduser())
        data["speechmatics_lang"] = self.lang_combo.currentText()
        cfg = Config(data)
        cfg.save()
        cfg.ensure_dirs()
        self.result_config = cfg

        try:
            if self.autostart_check.isChecked():
                autostart.enable()
            else:
                autostart.disable()
        except OSError:
            pass

        super().accept()
