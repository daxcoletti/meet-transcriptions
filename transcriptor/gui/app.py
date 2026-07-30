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

from .. import config, engine, i18n
from ..i18n import tr
from ..watcher import AudioWatcher
from .settings_dialog import SettingsDialog
from .wizard import run_wizard


_BADGE_COLORS = {"ok": "#2e9e4f", "warn": "#f0a500", "error": "#d63031"}


def _make_icon(badge=None):
    """Ícono de micrófono dibujado programáticamente (sin assets binarios).

    badge: None | "ok" | "warn" | "error" — agrega un distintivo de color en
    la esquina con el estado de las API keys (verde = completo, amarillo =
    falta transcripción o minuta, rojo = sin keys).
    """
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

    if badge:
        p.setPen(QPen(Qt.white, 3))
        p.setBrush(QColor(_BADGE_COLORS[badge]))
        p.drawEllipse(32, 32, 30, 30)  # distintivo, esquina inferior derecha
        p.setPen(QPen(Qt.white, 5))
        p.setBrush(Qt.NoBrush)
        if badge == "ok":
            # tilde ✓
            p.drawLine(39, 47, 45, 53)
            p.drawLine(45, 53, 55, 41)
        else:
            # signo de exclamación !
            p.drawLine(47, 38, 47, 49)
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.white)
            p.drawEllipse(44, 52, 6, 6)
    p.end()
    return QIcon(pm)


class _Bridge(QObject):
    """Puentea callbacks de hilos worker hacia el hilo de la GUI."""

    log_line = Signal(str)
    file_done = Signal(str, str)  # nombre, status ("ok"|"ok_no_minuta"|"fail")


class LogWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("log.title"))
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

        self.tray = QSystemTrayIcon(_make_icon())
        self._update_tray_status()
        self._build_menu()
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _update_tray_status(self):
        """Ícono con distintivo de color + tooltip según las keys configuradas."""
        has_t = self.cfg.has_transcription_key()
        has_m = self.cfg.has_minuta_key()
        if has_t and has_m:
            badge, tip = "ok", tr("tray.tip_ok")
        elif has_t:
            badge, tip = "warn", tr("tray.tip_no_minuta")
        elif has_m:
            badge, tip = "warn", tr("tray.tip_no_trans")
        else:
            badge, tip = "error", tr("tray.tip_no_keys")
        self.tray.setIcon(_make_icon(badge))
        self.tray.setToolTip(tip)

    def _build_menu(self):
        """(Re)arma el menú de la bandeja — se rehace si cambia el idioma."""
        menu = QMenu()
        menu.addAction(tr("tray.activity"), self._show_log)
        menu.addSeparator()
        menu.addAction(tr("tray.open_recordings"),
                       lambda: self._open_dir(self.cfg.audios_dir))
        menu.addAction(tr("tray.open_transcriptions"),
                       lambda: self._open_dir(self.cfg.transcriptions_dir))
        menu.addAction(tr("tray.open_minutas"),
                       lambda: self._open_dir(self.cfg.minutas_dir))
        menu.addSeparator()
        self.pause_action = QAction(tr("tray.pause"))
        self.pause_action.setCheckable(True)
        if self.watcher and self.watcher.paused:
            self.pause_action.setChecked(True)
            self.pause_action.setText(tr("tray.resume"))
        self.pause_action.toggled.connect(self._toggle_pause)
        menu.addAction(self.pause_action)
        menu.addAction(tr("tray.settings"), self._open_settings)
        menu.addSeparator()
        menu.addAction(tr("tray.quit"), self._quit)
        self._menu = menu  # mantener referencia (Qt no la retiene)
        self.tray.setContextMenu(menu)

    # --- Ciclo de vida ---
    def start(self):
        self.cfg.ensure_dirs()
        engine.configure(self.cfg)
        if engine.FFMPEG is None:
            engine.log(tr("log.no_ffmpeg"))
        self.watcher = AudioWatcher(self.cfg, on_file_done=self.bridge.file_done.emit)
        self.watcher.start()
        engine.log(tr("log.watching", dir=self.cfg.audios_dir))

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
            self.pause_action.setText(tr("tray.resume"))
        else:
            self.watcher.resume()
            self.pause_action.setText(tr("tray.pause"))

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, None)
        if dlg.exec() and dlg.result_config:
            self.cfg = dlg.result_config
            i18n.set_language(self.cfg.data.get("language", "auto"))
            self.log_window.setWindowTitle(tr("log.title"))
            self._update_tray_status()
            self._build_menu()
            self._restart_watcher()
            engine.log(tr("log.settings_updated"))

    # --- Notificaciones ---
    def _notify_done(self, name, status):
        if status == "ok":
            self.tray.showMessage(
                tr("notify.done.title"),
                tr("notify.done.body", name=name),
                QSystemTrayIcon.Information,
                8000,
            )
        elif status == "ok_no_minuta":
            self.tray.showMessage(
                tr("notify.nominuta.title"),
                tr("notify.nominuta.body", name=name),
                QSystemTrayIcon.Warning,
                15000,
            )
        else:
            self.tray.showMessage(
                tr("notify.fail.title"),
                tr("notify.fail.body", name=name),
                QSystemTrayIcon.Warning,
                8000,
            )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Meet Transcriptions")
    app.setQuitOnLastWindowClosed(False)

    i18n.set_language(config.load().data.get("language", "auto"))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Meet Transcriptions", tr("app.no_tray"))
        return 1

    if config.is_first_run():
        cfg = run_wizard()
        if cfg is None:
            return 0  # canceló el wizard: no dejar la app a medio configurar
    else:
        cfg = config.load()

    i18n.set_language(cfg.data.get("language", "auto"))
    tray_app = TrayApp(app, cfg)
    tray_app.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
