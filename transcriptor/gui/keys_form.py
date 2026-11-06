"""Formulario reutilizable de API keys (lo comparten el wizard y Configuración).

Proveedores de transcripción: hace falta al menos una key.
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from .. import validators
from ..config import TRANSCRIPTION_PROVIDERS
from ..i18n import tr

# (id, nombre, URL para conseguir la key)
TRANSCRIPTION_META = [
    ("deepgram", "Deepgram", "https://console.deepgram.com/"),
    ("gladia", "Gladia", "https://app.gladia.io/"),
    ("assemblyai", "AssemblyAI", "https://www.assemblyai.com/dashboard/"),
    ("elevenlabs", "ElevenLabs", "https://elevenlabs.io/app/settings/api-keys"),
    ("speechmatics", "Speechmatics", "https://portal.speechmatics.com/"),
    ("groq", "Groq", "https://console.groq.com/keys"),
]


class _KeyChecker(QThread):
    result = Signal(str, object, str)  # provider, ok (True/False/None), mensaje

    def __init__(self, provider, key, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._key = key

    def run(self):
        ok, msg = validators.check_key(self._provider, self._key)
        self.result.emit(self._provider, ok, msg)


class KeysForm(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.edits = {}
        self._status = {}
        self._checkers = []

        grid = QGridLayout(self)
        grid.setColumnStretch(1, 1)
        row = 0

        row = self._add_section(grid, row, tr("keys.section_transcription"))
        for pid, name, url in TRANSCRIPTION_META:
            row = self._add_provider(grid, row, pid, name, url)

    def _add_section(self, grid, row, text):
        label = QLabel(f"<b>{text}</b>")
        label.setStyleSheet("margin-top: 8px;")
        grid.addWidget(label, row, 0, 1, 5)
        return row + 1

    def _add_provider(self, grid, row, pid, name, url):
        label = QLabel(
            f'<a href="{url}">{name}</a><br>'
            f'<span style="color:gray; font-size:8pt">{tr("prov." + pid)}</span>'
        )
        label.setOpenExternalLinks(True)

        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.Password)
        edit.setMinimumWidth(160)
        edit.setPlaceholderText(tr("keys.placeholder"))
        edit.textChanged.connect(self.changed)
        self.edits[pid] = edit

        eye = QToolButton()
        eye.setText("👁")
        eye.setCheckable(True)
        eye.setToolTip(tr("keys.toggle_tip"))
        eye.toggled.connect(
            lambda show, e=edit: e.setEchoMode(
                QLineEdit.Normal if show else QLineEdit.Password
            )
        )

        test = QPushButton(tr("keys.test"))
        test.clicked.connect(lambda _=False, p=pid: self._test_key(p))

        status = QLabel("")
        status.setMinimumWidth(110)
        self._status[pid] = status

        grid.addWidget(label, row, 0)
        grid.addWidget(edit, row, 1)
        grid.addWidget(eye, row, 2)
        grid.addWidget(test, row, 3)
        grid.addWidget(status, row, 4)
        return row + 1

    # --- API ---
    def get_keys(self):
        return {
            pid: e.text().strip() for pid, e in self.edits.items() if e.text().strip()
        }

    def set_keys(self, keys):
        for pid, e in self.edits.items():
            e.setText(keys.get(pid, ""))

    def has_transcription_key(self):
        keys = self.get_keys()
        return any(p in keys for p in TRANSCRIPTION_PROVIDERS)

    # --- Validación ---
    def _test_key(self, provider):
        key = self.edits[provider].text().strip()
        status = self._status[provider]
        if not key:
            status.setText(f'<span style="color:gray">{tr("keys.empty")}</span>')
            return
        status.setText(tr("keys.testing"))
        checker = _KeyChecker(provider, key, self)
        checker.result.connect(self._on_result)
        checker.finished.connect(lambda c=checker: self._checkers.remove(c))
        self._checkers.append(checker)
        checker.start()

    def _on_result(self, provider, ok, msg):
        status = self._status[provider]
        if ok is True:
            status.setText(f'<span style="color:green">{tr("keys.valid")}</span>')
        elif ok is False:
            status.setText(f'<span style="color:red">{tr("keys.rejected")}</span>')
        else:
            status.setText(f'<span style="color:orange">{tr("keys.unknown")}</span>')
        status.setToolTip(msg)
