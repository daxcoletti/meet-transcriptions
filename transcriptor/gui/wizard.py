"""Wizard de primera ejecución: bienvenida → ffmpeg → API keys → carpeta → fin.

Se abre solo cuando todavía no existe config.json. La primera página tiene un
selector de idioma: al cambiarlo, el wizard se cierra con RESTART_CODE y
run_wizard() lo recrea con todos los textos en el idioma nuevo.
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from .. import autostart, config, i18n, shortcuts
from ..config import Config
from ..i18n import tr
from .ffmpeg_widget import FFmpegStatusWidget
from .keys_form import KeysForm

LANG_OPTIONS = [("auto", None), ("es", "Español"), ("en", "English")]


class _IntroPage(QWizardPage):
    def __init__(self, current_lang_value):
        super().__init__()
        self.setTitle(tr("wiz.intro.title"))
        text = QLabel(tr("wiz.intro.text"))
        text.setWordWrap(True)

        self.lang_combo = QComboBox()
        for value, label in LANG_OPTIONS:
            self.lang_combo.addItem(label or tr("lang.auto"), value)
        idx = next(
            (i for i, (v, _) in enumerate(LANG_OPTIONS) if v == current_lang_value), 0
        )
        self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(tr("wiz.intro.lang")))
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addStretch(1)
        layout.addLayout(lang_row)

    def _on_lang_changed(self, _index):
        # Recrear el wizard con el idioma nuevo (run_wizard lo maneja).
        wiz = self.wizard()
        wiz.pending_language = self.lang_combo.currentData()
        wiz.done(SetupWizard.RESTART_CODE)


class _FFmpegPage(QWizardPage):
    def __init__(self, cfg):
        super().__init__()
        self.setTitle(tr("wiz.ffmpeg.title"))
        self.setSubTitle(tr("wiz.ffmpeg.subtitle"))
        self.widget = FFmpegStatusWidget(cfg)
        self.widget.status_changed.connect(lambda _: self.completeChanged.emit())

        self.skip = QCheckBox(tr("wiz.ffmpeg.skip"))
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
        self.setTitle(tr("wiz.keys.title"))
        self.setSubTitle(tr("wiz.keys.subtitle"))
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
        self.setTitle(tr("wiz.folder.title"))
        self.setSubTitle(tr("wiz.folder.subtitle"))
        self.edit = QLineEdit(str(default_dir))
        browse = QPushButton(tr("wiz.folder.browse"))
        browse.clicked.connect(self._browse)

        row = QHBoxLayout()
        row.addWidget(self.edit, 1)
        row.addWidget(browse)

        note = QLabel(tr("wiz.folder.drop_note"))
        note.setWordWrap(True)

        self.desktop_check = QCheckBox(tr("wiz.folder.desktop_link"))
        self.desktop_check.setChecked(True)
        pin_key = "wiz.folder.pin_win" if os.name == "nt" else "wiz.folder.pin_linux"
        self.pin_check = QCheckBox(tr(pin_key))
        self.pin_check.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addSpacing(16)
        layout.addWidget(note)
        layout.addWidget(self.desktop_check)
        layout.addWidget(self.pin_check)
        layout.addStretch(1)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("wiz.folder.dialog"), self.edit.text()
        )
        if d:
            self.edit.setText(d)

    def isComplete(self):
        return bool(self.edit.text().strip())


class _FinalPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("wiz.final.title"))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.autostart = QCheckBox(tr("wiz.final.autostart"))
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

        sc = []
        if wiz.folder_page.desktop_check.isChecked():
            sc.append(tr("wiz.final.sc_desktop"))
        if wiz.folder_page.pin_check.isChecked():
            sc.append(
                tr("wiz.final.sc_pin_win" if os.name == "nt" else "wiz.final.sc_pin_linux")
            )
        lines = [
            tr("wiz.final.folder", folder=folder),
            tr("wiz.final.keys", n=n_keys),
            tr("wiz.final.ffmpeg_ok") if ffmpeg_ok else tr("wiz.final.ffmpeg_missing"),
            tr("wiz.final.shortcuts", what=" + ".join(sc) if sc else tr("wiz.final.sc_none")),
            "",
            tr("wiz.final.text"),
        ]
        self.summary.setText("<br>".join(lines))


class SetupWizard(QWizard):
    RESTART_CODE = 2  # cambio de idioma: recrear el wizard

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("wiz.title"))
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(760, 560)
        self.pending_language = cfg.data.get("language", "auto")

        self.ffmpeg_page = _FFmpegPage(cfg)
        self.keys_page = _KeysPage(cfg.api_keys)
        self.folder_page = _FolderPage(cfg.audios_dir)
        self.final_page = _FinalPage()

        self.addPage(_IntroPage(self.pending_language))
        self.addPage(self.ffmpeg_page)
        self.addPage(self.keys_page)
        self.addPage(self.folder_page)
        self.addPage(self.final_page)

        self._base = cfg

    def accept(self):
        data = dict(self._base.data)
        data["api_keys"] = self.keys_page.form.get_keys()
        data["audios_dir"] = str(Path(self.folder_page.edit.text().strip()).expanduser())
        data["language"] = self.pending_language
        cfg = Config(data)
        cfg.save()
        cfg.ensure_dirs()

        # Accesos directos para el drag & drop (fallar acá no es fatal).
        if self.folder_page.desktop_check.isChecked():
            shortcuts.create_desktop_link(cfg.audios_dir)
        if self.folder_page.pin_check.isChecked():
            shortcuts.pin_to_file_manager(cfg.audios_dir)

        try:
            if self.final_page.autostart.isChecked():
                autostart.enable()
            else:
                autostart.disable()
        except OSError:
            pass  # sin autostart no es fatal

        super().accept()


def run_wizard(parent=None):
    """Ejecuta el wizard (recreándolo si cambia el idioma).

    Devuelve la Config nueva, o None si se canceló.
    """
    language = None  # None = usar lo que diga la config
    while True:
        cfg = config.load()
        if language is not None:
            cfg.data["language"] = language
        i18n.set_language(cfg.data.get("language", "auto"))
        wiz = SetupWizard(cfg, parent)
        result = wiz.exec()
        if result == SetupWizard.RESTART_CODE:
            language = wiz.pending_language
            continue
        if result == QWizard.Accepted:
            return config.load()
        return None
