"""Diálogo de Configuración: secciones a la izquierda, opciones a la derecha.

Antes era una sola página apilada que obligaba a scrollear en un espacio
mínimo (sobre todo las API keys). Ahora: QListWidget (secciones) +
QStackedWidget (una página por sección), con las keys ocupando todo el
panel derecho.
"""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import autostart, shortcuts
from ..config import Config
from ..i18n import tr
from .ffmpeg_widget import FFmpegStatusWidget
from .keys_form import KeysForm

SPEECHMATICS_LANGS = ["en", "es", "pt", "fr", "de", "it"]
UI_LANGS = [("auto", None), ("es", "Español"), ("en", "English")]


def _page(title_key, hint_key=None):
    """Página base de una sección: título en negrita + hint opcional."""
    w = QWidget()
    layout = QVBoxLayout(w)
    title = QLabel(f"<h3>{tr(title_key)}</h3>")
    layout.addWidget(title)
    if hint_key:
        hint = QLabel(tr(hint_key))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)
    return w, layout


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("set.title"))
        self.setMinimumSize(900, 620)
        self._base = cfg
        self.result_config = None

        root = QVBoxLayout(self)
        body = QHBoxLayout()

        self.sections = QListWidget()
        self.sections.setFixedWidth(190)
        self.stack = QStackedWidget()

        for label_key, builder in [
            ("set.sec_keys", self._build_keys_page),
            ("set.sec_general", self._build_general_page),
            ("set.sec_recording", self._build_recording_page),
            ("set.sec_ffmpeg", self._build_ffmpeg_page),
        ]:
            self.sections.addItem(tr(label_key))
            self.stack.addWidget(builder(cfg))

        self.sections.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sections.setCurrentRow(0)

        body.addWidget(self.sections)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    def _build_keys_page(self, cfg):
        page, layout = _page("set.sec_keys", "set.keys_hint")
        self.keys_form = KeysForm()
        self.keys_form.set_keys(cfg.api_keys)
        scroll = QScrollArea()
        scroll.setWidget(self.keys_form)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll, 1)
        return page

    def _build_general_page(self, cfg):
        page, layout = _page("set.sec_general")
        form = QFormLayout()

        self.folder_edit = QLineEdit(str(cfg.audios_dir))
        browse = QPushButton(tr("wiz.folder.browse"))
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        form.addRow(tr("set.folder"), folder_row)

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

        self.ui_lang_combo = QComboBox()
        for value, label in UI_LANGS:
            self.ui_lang_combo.addItem(label or tr("lang.auto"), value)
        current = cfg.data.get("language", "auto")
        idx = next((i for i, (v, _) in enumerate(UI_LANGS) if v == current), 0)
        self.ui_lang_combo.setCurrentIndex(idx)
        form.addRow(tr("set.ui_lang"), self.ui_lang_combo)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(SPEECHMATICS_LANGS)
        if cfg.speechmatics_lang in SPEECHMATICS_LANGS:
            self.lang_combo.setCurrentText(cfg.speechmatics_lang)
        self.lang_combo.setToolTip(tr("set.lang_speechmatics_tip"))
        form.addRow(tr("set.lang_speechmatics"), self.lang_combo)

        self.autostart_check = QCheckBox(tr("set.autostart"))
        self.autostart_check.setChecked(autostart.is_enabled())
        form.addRow("", self.autostart_check)

        self.debug_check = QCheckBox(tr("set.debug_log"))
        self.debug_check.setChecked(bool(cfg.data.get("debug_log", True)))
        self.debug_check.setToolTip(tr("set.debug_log_tip"))
        form.addRow("", self.debug_check)

        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_recording_page(self, cfg):
        page, layout = _page("set.sec_recording")
        form = QFormLayout()

        # El atajo primero: es lo que más se busca acá.
        self.hotkey_edit = QKeySequenceEdit(
            QKeySequence(cfg.data.get("record_hotkey", ""))
        )
        hotkey_clear = QPushButton(tr("set.hotkey_clear"))
        hotkey_clear.clicked.connect(self.hotkey_edit.clear)
        hk_row = QHBoxLayout()
        hk_row.addWidget(self.hotkey_edit, 1)
        hk_row.addWidget(hotkey_clear)
        form.addRow(tr("set.hotkey"), hk_row)
        hk_hint = QLabel(tr("set.hotkey_tip"))
        hk_hint.setWordWrap(True)
        hk_hint.setStyleSheet("color: gray;")
        form.addRow("", hk_hint)

        self.rec_quality = QComboBox()
        self.rec_quality.addItem(tr("set.rec_q_low"), "low")
        self.rec_quality.addItem(tr("set.rec_q_medium"), "medium")
        current_q = cfg.data.get("record_quality", "low")
        self.rec_quality.setCurrentIndex(0 if current_q == "low" else 1)
        form.addRow(tr("set.rec_quality"), self.rec_quality)

        self.rec_mic = QCheckBox(tr("set.rec_mic"))
        self.rec_mic.setChecked(bool(cfg.data.get("record_mic", True)))
        form.addRow("", self.rec_mic)

        self.rec_system = QCheckBox(tr("set.rec_system"))
        self.rec_system.setChecked(bool(cfg.data.get("record_system", True)))
        form.addRow("", self.rec_system)

        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_ffmpeg_page(self, cfg):
        page, layout = _page("set.sec_ffmpeg")
        layout.addWidget(FFmpegStatusWidget(cfg))
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
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
        data["debug_log"] = self.debug_check.isChecked()
        # QKeySequenceEdit puede capturar varias combinaciones: usar la primera.
        data["record_hotkey"] = (
            self.hotkey_edit.keySequence().toString().split(",")[0].strip()
        )
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
