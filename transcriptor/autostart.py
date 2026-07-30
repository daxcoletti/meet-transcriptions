"""Arranque automático con la sesión del usuario (Windows y Linux)."""

import os
import sys
from pathlib import Path

APP_KEY = "MeetTranscriptions"


def _launch_command():
    """Comando que arranca la GUI, según cómo esté instalada la app."""
    if getattr(sys, "frozen", False):
        # Empaquetada con PyInstaller: el propio exe.
        return f'"{sys.executable}"'
    # Instalación desde código: python -m transcriptor (pythonw en Windows
    # para no abrir consola).
    py = Path(sys.executable)
    if os.name == "nt":
        pyw = py.with_name("pythonw.exe")
        if pyw.exists():
            py = pyw
    return f'"{py}" -m transcriptor'


def is_enabled():
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
            ) as k:
                winreg.QueryValueEx(k, APP_KEY)
                return True
        except OSError:
            return False
    return _desktop_file().exists()


def enable():
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            winreg.SetValueEx(k, APP_KEY, 0, winreg.REG_SZ, _launch_command())
        return

    f = _desktop_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Meet Transcriptions\n"
        f"Exec={_launch_command()}\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


def disable():
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as k:
                winreg.DeleteValue(k, APP_KEY)
        except OSError:
            pass
        return
    try:
        _desktop_file().unlink()
    except OSError:
        pass


def _desktop_file():
    return Path.home() / ".config" / "autostart" / "meet-transcriptions.desktop"
