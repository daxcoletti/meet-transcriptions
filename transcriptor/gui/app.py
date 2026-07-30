"""Aplicación de bandeja del sistema: vigila la carpeta y muestra actividad.

No hay ventana principal permanente: la app vive junto al reloj. Desde el
menú se abre el registro de actividad, la configuración y las carpetas de
resultados.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSystemTrayIcon,
)

from .. import __version__, config, engine, ffmpeg_utils, i18n, updater
from .. import hotkey as hotkey_mod
from .. import recorder as recorder_mod
from ..i18n import tr
from ..recorder import RecordingError, ScreenRecorder
from ..watcher import AudioWatcher
from .settings_dialog import SettingsDialog
from .wizard import run_wizard


def _fmt_elapsed(seconds):
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _open_external(target):
    """Abre una carpeta o URL con la app del sistema.

    En la app congelada de Linux no usamos QDesktopServices: lanzaría
    xdg-open con el LD_LIBRARY_PATH del bundle y el navegador/gestor de
    archivos puede morir con librerías incompatibles (mismo problema que
    ffmpeg). Lo lanzamos nosotros con el entorno limpio.
    """
    if sys.platform.startswith("linux") and getattr(sys, "frozen", False):
        try:
            subprocess.Popen(
                ["xdg-open", str(target)], env=ffmpeg_utils.subprocess_env()
            )
            return
        except OSError:
            pass  # sin xdg-open: caer a Qt
    s = str(target)
    url = QUrl(s) if s.startswith(("http://", "https://")) else QUrl.fromLocalFile(s)
    QDesktopServices.openUrl(url)


_BADGE_COLORS = {
    "ok": "#2e9e4f", "warn": "#f0a500", "error": "#d63031",
    "busy": "#1976d2", "rec": "#e02b2b",
}


def _make_icon(badge=None, spin=0):
    """Ícono de micrófono dibujado programáticamente (sin assets binarios).

    badge: None | "ok" | "warn" | "error" | "busy" — distintivo de color en
    la esquina: estado de las API keys (verde = completo, amarillo = falta
    transcripción o minuta, rojo = sin keys) o actividad ("busy": spinner
    azul; `spin` 0-3 rota el arco para animarlo).
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
        if badge == "rec":
            # punto de grabación: alterna lleno/anillo para "pulsar"
            if spin % 2 == 0:
                p.setPen(Qt.NoPen)
                p.setBrush(Qt.white)
                p.drawEllipse(41, 41, 12, 12)
            else:
                p.setPen(QPen(Qt.white, 3))
                p.drawEllipse(42, 42, 10, 10)
        elif badge == "busy":
            # spinner: arco que rota según `spin`
            p.drawArc(38, 38, 18, 18, -spin * 90 * 16, 220 * 16)
        elif badge == "ok":
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
    progress = Signal(object)     # dict de progreso del engine (archivo, etapa, ...)
    record_done = Signal(object)  # {"path": str|None, "error": str|None}
    hotkey_pressed = Signal()     # atajo global grabar/detener (desde el hilo de pynput)
    update_checked = Signal(object)  # {"info": dict|None, "manual": bool, "error": str|None}
    update_ready = Signal(object)    # {"path": str|None, "error": str|None}


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
        self.bridge.progress.connect(self._on_progress)
        self.bridge.record_done.connect(self._on_record_done)
        self.bridge.hotkey_pressed.connect(self._on_hotkey)
        self.bridge.update_checked.connect(self._on_update_checked)
        self.bridge.update_ready.connect(self._on_update_ready)
        engine.set_log_callback(self.bridge.log_line.emit)
        engine.set_progress_callback(self.bridge.progress.emit)

        self.watcher = None
        self.update_info = None  # release más nuevo detectado (dict de updater)

        # Estado de actividad para el spinner de la bandeja
        self._busy = None   # dict de progreso mientras procesa, None si ocioso
        self._spin = 0
        self._spin_timer = QTimer()
        self._spin_timer.setInterval(350)
        self._spin_timer.timeout.connect(self._spin_tick)

        # Grabación de pantalla
        self.recorder = None
        self.hotkey = None
        self._rec_timer = QTimer()
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._rec_tick)

        self.tray = QSystemTrayIcon(_make_icon())
        self._update_tray_status()
        self._build_menu()
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # --- Atajo global ---
    def _setup_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        seq = self.cfg.data.get("record_hotkey", "")
        if not seq:
            return
        if not hotkey_mod.available():
            engine.log(tr("hotkey.unavailable"))
            return
        try:
            self.hotkey = hotkey_mod.HotkeyListener(
                seq, self.bridge.hotkey_pressed.emit
            )
            self.hotkey.start()
            engine.log(tr("hotkey.active", combo=seq))
        except Exception as e:
            self.hotkey = None
            engine.log(tr("hotkey.failed", combo=seq, err=e))

    def _on_hotkey(self):
        # Ignorar mientras se está guardando una grabación (acción deshabilitada).
        if self.record_action.isEnabled():
            self._toggle_recording()

    # --- Grabación de pantalla ---
    def _toggle_recording(self):
        if self.recorder and self.recorder.recording:
            # Detener: el mux/mover puede tardar unos segundos → hilo aparte.
            self._rec_timer.stop()
            self.record_action.setText(tr("rec.stopping"))
            self.record_action.setEnabled(False)
            rec = self.recorder

            def worker():
                try:
                    path = rec.stop()
                    self.bridge.record_done.emit({"path": str(path), "error": None})
                except Exception as e:
                    self.bridge.record_done.emit({"path": None, "error": str(e)})

            threading.Thread(target=worker, daemon=True).start()
            return

        kind = recorder_mod.session_kind()
        if kind == "wayland":
            QMessageBox.information(None, "Meet Transcriptions", tr("rec.wayland"))
            return

        self.recorder = ScreenRecorder(self.cfg, log=engine.log)
        size = None
        if kind == "x11":
            screen = self.app.primaryScreen()
            geo = screen.virtualGeometry()
            ratio = screen.devicePixelRatio()
            size = (int(geo.width() * ratio), int(geo.height() * ratio))
        try:
            self.recorder.start(screen_size=size)
        except RecordingError as e:
            msg = tr("rec.wayland") if str(e) == "wayland" else tr("rec.failed", err=e)
            engine.log(msg)
            QMessageBox.warning(None, "Meet Transcriptions", msg)
            self.recorder = None
            return
        self._rec_timer.start()
        self._rec_tick()
        seq = self.cfg.data.get("record_hotkey", "")
        self.tray.showMessage(
            tr("rec.started.title"),
            tr("rec.started.body_hotkey", hotkey=seq) if seq else tr("rec.started.body"),
            QSystemTrayIcon.Information,
            5000,
        )

    def _rec_tick(self):
        if not (self.recorder and self.recorder.recording):
            return
        if self.recorder.video_died():
            # ffmpeg murió solo: rescatar lo grabado hasta el corte.
            engine.log("⚠️  El ffmpeg de grabación terminó inesperadamente; rescato lo grabado…")
            self._toggle_recording()  # entra por la rama de stop
            return
        t = _fmt_elapsed(self.recorder.elapsed())
        self._spin = (self._spin + 1) % 4
        self.tray.setIcon(_make_icon("rec", self._spin))
        self.tray.setToolTip(tr("rec.tip", time=t))
        self.record_action.setText(tr("rec.stop", time=t))

    def _on_record_done(self, result):
        self.record_action.setEnabled(True)
        self.record_action.setText(tr("rec.start"))
        self.recorder = None
        self._update_tray_status_or_busy()
        if result["error"]:
            engine.log(tr("rec.failed", err=result["error"]))
            self.tray.showMessage(
                "Meet Transcriptions", tr("rec.failed", err=result["error"]),
                QSystemTrayIcon.Warning, 10000,
            )
        else:
            name = Path(result["path"]).name
            engine.log(tr("rec.saved", name=name))
            # El watcher ve el archivo movido y arranca la transcripción solo.

    def _recording_active(self):
        return bool(self.recorder and self.recorder.recording)

    def _update_tray_status_or_busy(self):
        """Restablece el ícono al estado que corresponda (procesando o keys)."""
        if self._busy:
            self._on_progress(self._busy)
        else:
            self._update_tray_status()

    # --- Actividad en la bandeja ---
    def _on_progress(self, data):
        """El engine avanzó de etapa: spinner + tooltip con lo que está haciendo."""
        self._busy = data
        if self._recording_active():
            return  # el punto rojo de grabación tiene prioridad visual
        stage_raw = data.get("etapa") or ""
        stage_key = f"stage.{stage_raw}"
        stage = tr(stage_key) if stage_key in i18n.STRINGS else stage_raw
        seg, total = data.get("segmento"), data.get("segmentos_total")
        if seg and total:
            stage += f" ({seg}/{total})"
        self.tray.setToolTip(tr("tray.tip_busy", file=data.get("archivo", "?"), stage=stage))
        if not self._spin_timer.isActive():
            self.tray.setIcon(_make_icon("busy", self._spin))
            self._spin_timer.start()

    def _spin_tick(self):
        self._spin = (self._spin + 1) % 4
        self.tray.setIcon(_make_icon("busy", self._spin))

    def _update_tray_status(self):
        """Ícono con distintivo de color + tooltip según las keys configuradas."""
        if self._busy or self._recording_active():
            return  # procesando o grabando: ese estado manda
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
        seq = self.cfg.data.get("record_hotkey", "")
        label = tr("rec.start") + (f"  ({seq})" if seq else "")
        self.record_action = QAction(label)
        if self.recorder and self.recorder.recording:
            self.record_action.setText(
                tr("rec.stop", time=_fmt_elapsed(self.recorder.elapsed()))
            )
        self.record_action.triggered.connect(self._toggle_recording)
        menu.addAction(self.record_action)
        menu.addSeparator()
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
        menu.addAction(tr("tray.open_logs"),
                       lambda: self._open_dir(config.DATA_DIR))
        menu.addSeparator()
        if self.update_info:
            menu.addAction(
                tr("upd.menu_update", version=self.update_info["version"]),
                self._start_update,
            )
        else:
            menu.addAction(
                tr("upd.menu_check"), lambda: self._check_updates(manual=True)
            )
        menu.addAction(tr("tray.quit"), self._quit)
        self._menu = menu  # mantener referencia (Qt no la retiene)
        self.tray.setContextMenu(menu)

    # --- Ciclo de vida ---
    def start(self):
        self.cfg.ensure_dirs()
        engine.configure(self.cfg)
        if engine.FFMPEG is None:
            engine.log(tr("log.no_ffmpeg"))
        # Rescatar grabaciones interrumpidas ANTES de arrancar el watcher,
        # así los archivos recuperados entran por el barrido inicial. Primero
        # matar ffmpeg huérfanos: si siguen grabando, tienen los archivos
        # agarrados y la recuperación falla con "en uso por otro proceso".
        recorder_mod.kill_orphan_ffmpeg(self.cfg, log=engine.log)
        recorder_mod.recover_orphans(self.cfg, log=engine.log)
        self.watcher = AudioWatcher(self.cfg, on_file_done=self.bridge.file_done.emit)
        self.watcher.start()
        engine.log(tr("log.watching", dir=self.cfg.audios_dir))

        self._setup_hotkey()

        # Buscar actualizaciones: a los 15 s del arranque y luego cada 24 h.
        QTimer.singleShot(15_000, lambda: self._check_updates(manual=False))
        self._update_timer = QTimer()
        self._update_timer.setInterval(24 * 60 * 60 * 1000)
        self._update_timer.timeout.connect(lambda: self._check_updates(manual=False))
        self._update_timer.start()

    def _restart_watcher(self):
        if self.watcher:
            self.watcher.stop()
        self.start()

    def _quit(self):
        if self.hotkey:
            self.hotkey.stop()
        if self._recording_active():
            # Cerrar con gracia: finalizar el MKV y moverlo a la carpeta
            # vigilada; se transcribe en el próximo arranque (barrido inicial).
            try:
                self.recorder.stop()
            except Exception:
                pass
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
        _open_external(path)

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
            apply_debug_log_setting(self.cfg)
            i18n.set_language(self.cfg.data.get("language", "auto"))
            self.log_window.setWindowTitle(tr("log.title"))
            self._update_tray_status()
            self._build_menu()
            self._setup_hotkey()
            self._restart_watcher()
            engine.log(tr("log.settings_updated"))

    # --- Actualizaciones ---
    def _check_updates(self, manual=False):
        def worker():
            try:
                info = updater.check_latest()
                self.bridge.update_checked.emit(
                    {"info": info, "manual": manual, "error": None}
                )
            except Exception as e:
                self.bridge.update_checked.emit(
                    {"info": None, "manual": manual, "error": str(e)}
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_checked(self, result):
        if result["error"]:
            if result["manual"]:
                engine.log(tr("upd.error", err=result["error"]))
            return  # chequeo automático fallido: silencioso (sin red, etc.)
        info = result["info"]
        if info is None:
            if result["manual"]:
                self.tray.showMessage(
                    tr("upd.none.title"),
                    tr("upd.none.body", current=__version__),
                    QSystemTrayIcon.Information,
                    6000,
                )
            return
        self.update_info = info
        self._build_menu()  # el ítem pasa a "Actualizar a la versión X"
        self.tray.showMessage(
            tr("upd.available.title"),
            tr("upd.available.body", version=info["version"], current=__version__),
            QSystemTrayIcon.Information,
            15000,
        )

    def _confirm_update(self, info):
        """Diálogo de confirmación previo: nada se instala sin un OK explícito."""
        box = QMessageBox(
            QMessageBox.Question,
            tr("upd.confirm.title"),
            tr("upd.confirm.body", version=info["version"], current=__version__),
        )
        yes = box.addButton(tr("upd.confirm.yes"), QMessageBox.AcceptRole)
        box.addButton(tr("upd.confirm.no"), QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def _start_update(self):
        info = self.update_info
        if not info:
            return
        if not updater.can_self_update() or not info.get("installer_url"):
            # Desde código (Linux/dev) no hay auto-update: abrir el release.
            _open_external(info["page_url"])
            return
        if not self._confirm_update(info):
            return
        engine.log(tr("upd.downloading", version=info["version"]))

        def worker():
            try:
                path = updater.download_installer(info["installer_url"])
                self.bridge.update_ready.emit({"path": str(path), "error": None})
            except Exception as e:
                self.bridge.update_ready.emit({"path": None, "error": str(e)})

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_ready(self, result):
        if result["error"]:
            engine.log(tr("upd.dl_error", err=result["error"]))
            return
        self.tray.showMessage(
            tr("upd.installing.title"),
            tr("upd.installing.body"),
            QSystemTrayIcon.Information,
            8000,
        )
        engine.log(tr("upd.installing.body"))
        updater.launch_installer(result["path"])
        self._quit()  # el instalador reemplaza los archivos y reabre la app

    # --- Notificaciones ---
    def _notify_done(self, name, status):
        # Fin de la actividad: apagar el spinner y volver al badge de keys.
        self._busy = None
        self._spin_timer.stop()
        self._update_tray_status()
        if status == "ok":
            self.tray.showMessage(
                tr("notify.done.title"),
                tr("notify.done.body", name=name),
                QSystemTrayIcon.Information,
                8000,
            )
        elif status == "no_audio":
            self.tray.showMessage(
                tr("notify.noaudio.title"),
                tr("notify.noaudio.body", name=name),
                QSystemTrayIcon.Warning,
                10000,
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


_crash_log_handle = None  # mantener la referencia viva para faulthandler


def _enable_diagnostics(cfg):
    """Crash log (fallos nativos con traceback) + log de la app en archivo.

    Van al directorio de datos del usuario (%LOCALAPPDATA%\\MeetTranscriptions
    en Windows, ~/.local/share/MeetTranscriptions en Linux) — accesible desde
    el menú «Abrir registros». El crash.log va siempre (faulthandler no
    cuesta nada hasta que hay un crash); el app.log se puede apagar en
    Configuración ("debug_log").
    """
    global _crash_log_handle
    import faulthandler

    from ..config import DATA_DIR

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _crash_log_handle = open(DATA_DIR / "crash.log", "a", buffering=1)
        _crash_log_handle.write(
            f"--- inicio {__version__} {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
        faulthandler.enable(_crash_log_handle)
    except OSError:
        pass
    if cfg.data.get("debug_log", True):
        engine.enable_file_log(DATA_DIR / "app.log")
    engine.log(f"— Meet Transcriptions {__version__} iniciada —")


def apply_debug_log_setting(cfg):
    """Prende/apaga el app.log en caliente según la config."""
    from ..config import DATA_DIR

    if cfg.data.get("debug_log", True):
        engine.enable_file_log(DATA_DIR / "app.log")
    else:
        engine.disable_file_log()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Meet Transcriptions")
    app.setQuitOnLastWindowClosed(False)
    _enable_diagnostics(config.load())

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
