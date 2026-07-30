"""Diálogo de Configuración: keys, carpeta, accesos directos, idioma, autostart."""

import os
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
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from .. import autostart, shortcuts
from ..config import Config
from ..i18n import tr
from .ffmpeg_widget import FFmpegStatusWidget
from .keys_form import KeysForm

SPEECHMATICS_LANGS = ["en", "es", "pt", "fr", "de", "it"]
UI_LANGS = [("auto", None), ("es", "Español"), ("en", "English")]


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("set.title"))
        self.setMinimumSize(780, 680)
        self._base = cfg
        self.result_config = None

        layout = QVBoxLayout(self)

        # --- API keys ---
        keys_box = QGroupBox(tr("set.keys_group"))
        self.keys_form = KeysForm()
        self.keys_form.set_keys(cfg.api_keys)
        scroll = QScrollArea()
        scroll.setWidget(self.keys_form)
        scroll.setWidgetResizable(True)
        kb_layout = QVBoxLayout(keys_box)
        kb_layout.addWidget(scroll)
        layout.addWidget(keys_box, 1)

        # --- Opciones generales ---
        general = QGroupBox(tr("set.general"))
        form = QFormLayout(general)

        self.folder_edit = QLineEdit(str(cfg.audios_dir))
        browse = QPushButton(tr("wiz.folder.browse"))
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        form.addRow(tr("set.folder"), folder_row)

        # Accesos directos a la carpeta (efecto inmediato, con feedback en el botón)
        self.desktop_btn = QPushButton(tr("set.make_desktop"))
        self.desktop_btn.clicked.connect(
            lambda: self._make_shortcut(self.desktop_btn, shortcuts.create_desktop_link)
        )
        pin_key = "set.make_pin_win" if os.name == "nt" else "set.make_pin_linux"
        self.pin_btn = QPushButton(tr(pin_key))
        self.pin_btn.clicked.connect(
            lambda: self._make_shortcut(self.pin_btn, shortcuts.pin_to_file_manager)
        )
        sc_row = QHBoxLayout()
        sc_row.addWidget(self.desktop_btn)
        sc_row.addWidget(self.pin_btn)
        sc_row.addStretch(1)
        form.addRow(tr("set.shortcuts"), sc_row)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(SPEECHMATICS_LANGS)
        if cfg.speechmatics_lang in SPEECHMATICS_LANGS:
            self.lang_combo.setCurrentText(cfg.speechmatics_lang)
        self.lang_combo.setToolTip(tr("set.lang_speechmatics_tip"))
        form.addRow(tr("set.lang_speechmatics"), self.lang_combo)

        self.ui_lang_combo = QComboBox()
        for value, label in UI_LANGS:
            self.ui_lang_combo.addItem(label or tr("lang.auto"), value)
        current = cfg.data.get("language", "auto")
        idx = next((i for i, (v, _) in enumerate(UI_LANGS) if v == current), 0)
        self.ui_lang_combo.setCurrentIndex(idx)
        form.addRow(tr("set.ui_lang"), self.ui_lang_combo)

        self.autostart_check = QCheckBox(tr("set.autostart"))
        self.autostart_check.setChecked(autostart.is_enabled())
        form.addRow("", self.autostart_check)

        layout.addWidget(general)

        # --- Grabación de pantalla ---
        rec_box = QGroupBox(tr("set.rec_group"))
        rec_form = QFormLayout(rec_box)
        self.rec_quality = QComboBox()
        self.rec_quality.addItem(tr("set.rec_q_low"), "low")
        self.rec_quality.addItem(tr("set.rec_q_medium"), "medium")
        current_q = cfg.data.get("record_quality", "low")
        self.rec_quality.setCurrentIndex(0 if current_q == "low" else 1)
        rec_form.addRow(tr("set.rec_quality"), self.rec_quality)
        self.rec_mic = QCheckBox(tr("set.rec_mic"))
        self.rec_mic.setChecked(bool(cfg.data.get("record_mic", True)))
        rec_form.addRow("", self.rec_mic)
        self.rec_system = QCheckBox(tr("set.rec_system"))
        self.rec_system.setChecked(bool(cfg.data.get("record_system", True)))
        rec_form.addRow("", self.rec_system)
        layout.addWidget(rec_box)

        # --- ffmpeg ---
        ffmpeg_box = QGroupBox(tr("set.ffmpeg_group"))
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
            self, tr("wiz.folder.dialog"), self.folder_edit.text()
        )
        if d:
            self.folder_edit.setText(d)

    def _current_folder(self):
        folder = Path(self.folder_edit.text().strip()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _make_shortcut(self, button, fn):
        ok = fn(self._current_folder())
        button.setText(tr("sc.ok") if ok else tr("sc.fail"))
        button.setEnabled(False)

    def accept(self):
        data = dict(self._base.data)
        data["api_keys"] = self.keys_form.get_keys()
        data["audios_dir"] = str(Path(self.folder_edit.text().strip()).expanduser())
        data["speechmatics_lang"] = self.lang_combo.currentText()
        data["language"] = self.ui_lang_combo.currentData()
        data["record_quality"] = self.rec_quality.currentData()
        data["record_mic"] = self.rec_mic.isChecked()
        data["record_system"] = self.rec_system.isChecked()
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
