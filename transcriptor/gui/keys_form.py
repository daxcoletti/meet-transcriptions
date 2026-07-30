"""Formulario reutilizable de API keys (lo comparten el wizard y Configuración)."""

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

# (id, nombre, URL para conseguir la key, para qué se usa)
PROVIDERS_META = [
    ("deepgram", "Deepgram", "https://console.deepgram.com/",
     "Transcripción + diarización (preferido)"),
    ("gladia", "Gladia", "https://app.gladia.io/",
     "Transcripción + diarización"),
    ("assemblyai", "AssemblyAI", "https://www.assemblyai.com/dashboard/",
     "Transcripción + diarización"),
    ("elevenlabs", "ElevenLabs", "https://elevenlabs.io/app/settings/api-keys",
     "Transcripción + diarización (Scribe)"),
    ("speechmatics", "Speechmatics", "https://portal.speechmatics.com/",
     "Transcripción + diarización"),
    ("groq", "Groq", "https://console.groq.com/keys",
     "Transcripción Whisper + minuta de respaldo"),
    ("gemini", "Google Gemini", "https://aistudio.google.com/apikey",
     "Minuta (primario, contexto de 1M)"),
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

        for row, (pid, name, url, desc) in enumerate(PROVIDERS_META):
            label = QLabel(
                f'<a href="{url}">{name}</a><br>'
                f'<span style="color:gray; font-size:8pt">{desc}</span>'
            )
            label.setOpenExternalLinks(True)

            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password)
            edit.setPlaceholderText("(sin configurar)")
            edit.textChanged.connect(self.changed)
            self.edits[pid] = edit

            eye = QToolButton()
            eye.setText("👁")
            eye.setCheckable(True)
            eye.setToolTip("Mostrar/ocultar la key")
            eye.toggled.connect(
                lambda show, e=edit: e.setEchoMode(
                    QLineEdit.Normal if show else QLineEdit.Password
                )
            )

            test = QPushButton("Probar")
            test.clicked.connect(lambda _=False, p=pid: self._test_key(p))

            status = QLabel("")
            status.setMinimumWidth(110)
            self._status[pid] = status

            grid.addWidget(label, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(eye, row, 2)
            grid.addWidget(test, row, 3)
            grid.addWidget(status, row, 4)

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
            status.setText('<span style="color:gray">vacía</span>')
            return
        status.setText("⏳ probando…")
        checker = _KeyChecker(provider, key, self)
        checker.result.connect(self._on_result)
        checker.finished.connect(lambda c=checker: self._checkers.remove(c))
        self._checkers.append(checker)
        checker.start()

    def _on_result(self, provider, ok, msg):
        status = self._status[provider]
        if ok is True:
            status.setText('<span style="color:green">✔ válida</span>')
        elif ok is False:
            status.setText('<span style="color:red">✘ rechazada</span>')
        else:
            status.setText('<span style="color:orange">? sin verificar</span>')
        status.setToolTip(msg)
