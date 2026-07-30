"""Aplicación de bandeja del sistema: vigila la carpeta y muestra actividad.

No hay ventana principal permanente: la app vive junto al reloj. Desde el
menú se abre el registro de actividad, la configuración y las carpetas de
resultados.
"""

import sys

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSystemTrayIcon,
)

from .. import config, engine
from ..watcher import AudioWatcher
from .settings_dialog import SettingsDialog
from .wizard import run_wizard


def _make_icon():
    """Ícono de micrófono dibujado programáticamente (sin assets binarios)."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0e7a5f"))
    p.drawEllipse(2, 2, 60, 60)
    p.setBrush(Qt.white)
    p.drawRoundedRect(26, 13, 12, 24, 6, 6)  # cápsula del micrófono
    pen = QPen(Qt.white, 4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(19, 20, 26, 24, 180 * 16, 180 * 16)  # soporte
    p.drawLine(32, 44, 32, 51)                     # pie
    p.end()
    return QIcon(pm)


class _Bridge(QObject):
    """Puentea callbacks de hilos worker hacia el hilo de la GUI."""

    log_line = Signal(str)
    file_done = Signal(str, bool)


class LogWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meet Transcriptions — Actividad")
        self.resize(820, 480)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        self.setCentralWidget(self.text)

    def append(self, line):
        self.text.appendPlainText(line)

    def closeEvent(self, event):
        # Ocultar en vez de cerrar: la app sigue viva en la bandeja.
        event.ignore()
        self.hide()


class TrayApp:
    def __init__(self, app, cfg):
        self.app = app
        self.cfg = cfg
        self.log_window = LogWindow()

        self.bridge = _Bridge()
        self.bridge.log_line.connect(self.log_window.append)
        self.bridge.file_done.connect(self._notify_done)
        engine.set_log_callback(self.bridge.log_line.emit)

        self.watcher = None

        icon = _make_icon()
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Meet Transcriptions")

        menu = QMenu()
        menu.addAction("Ver actividad", self._show_log)
        menu.addSeparator()
        menu.addAction("Abrir carpeta de grabaciones",
                       lambda: self._open_dir(self.cfg.audios_dir))
        menu.addAction("Abrir transcripciones",
                       lambda: self._open_dir(self.cfg.transcriptions_dir))
        menu.addAction("Abrir minutas",
                       lambda: self._open_dir(self.cfg.minutas_dir))
        menu.addSeparator()
        self.pause_action = QAction("Pausar procesamiento")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._toggle_pause)
        menu.addAction(self.pause_action)
        menu.addAction("Configuración…", self._open_settings)
        menu.addSeparator()
        menu.addAction("Salir", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # --- Ciclo de vida ---
    def start(self):
        self.cfg.ensure_dirs()
        engine.configure(self.cfg)
        if engine.FFMPEG is None:
            engine.log(
                "⚠️  ffmpeg no está disponible: los audios nuevos van a "
                "fallar hasta instalarlo (ver Configuración)."
            )
        self.watcher = AudioWatcher(self.cfg, on_file_done=self.bridge.file_done.emit)
        self.watcher.start()
        engine.log(f"👀 Vigilando {self.cfg.audios_dir} (eventos nativos del sistema).")

    def _restart_watcher(self):
        if self.watcher:
            self.watcher.stop()
        self.start()

    def _quit(self):
        if self.watcher:
            self.watcher.stop()
        self.tray.hide()
        self.app.quit()

    # --- Acciones del menú ---
    def _show_log(self):
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_log()

    def _open_dir(self, path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _toggle_pause(self, checked):
        if not self.watcher:
            return
        if checked:
            self.watcher.pause()
            self.pause_action.setText("Reanudar procesamiento")
        else:
            self.watcher.resume()
            self.pause_action.setText("Pausar procesamiento")

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, None)
        if dlg.exec() and dlg.result_config:
            self.cfg = dlg.result_config
            self._restart_watcher()
            engine.log("⚙️  Configuración actualizada.")

    # --- Notificaciones ---
    def _notify_done(self, name, ok):
        if ok:
            self.tray.showMessage(
                "Transcripción lista",
                f"{name}: transcripción y minuta generadas.",
                QSystemTrayIcon.Information,
                8000,
            )
        else:
            self.tray.showMessage(
                "Transcripción fallida",
                f"{name}: no se pudo procesar (ver actividad).",
                QSystemTrayIcon.Warning,
                8000,
            )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Meet Transcriptions")
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, "Meet Transcriptions",
            "No hay bandeja del sistema disponible en este entorno."
        )
        return 1

    if config.is_first_run():
        cfg = run_wizard()
        if cfg is None:
            return 0  # canceló el wizard: no dejar la app a medio configurar
    else:
        cfg = config.load()

    tray_app = TrayApp(app, cfg)
    tray_app.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
