"""Accesos directos a la carpeta de grabaciones, para que el drag & drop
quede obvio: enlace en el Escritorio y anclado al panel del explorador
(Acceso rápido en Windows, marcadores GTK en Linux).

Todas las funciones devuelven True/False y no lanzan: fallar acá nunca debe
frenar la configuración de la app.
"""

import os
import subprocess
from pathlib import Path

from .ffmpeg_utils import SUBPROCESS_FLAGS


def _powershell(script):
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            **SUBPROCESS_FLAGS,
        )
        return proc
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ps_quote(path):
    """Comillas simples de PowerShell: se escapan duplicándolas."""
    return str(path).replace("'", "''")


def desktop_dir():
    """Ruta real del Escritorio (contempla la redirección a OneDrive en Windows)."""
    if os.name == "nt":
        proc = _powershell("[Environment]::GetFolderPath('Desktop')")
        if proc and proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
        return Path.home() / "Desktop"

    try:
        proc = subprocess.run(
            ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    for name in ("Desktop", "Escritorio"):
        d = Path.home() / name
        if d.is_dir():
            return d
    return Path.home() / "Desktop"


def create_desktop_link(target):
    """Acceso directo a `target` en el Escritorio (.lnk en Windows, symlink en Linux)."""
    try:
        target = Path(target)
        desk = desktop_dir()
        if os.name == "nt":
            lnk = desk / f"{target.name}.lnk"
            proc = _powershell(
                f"$s = (New-Object -ComObject WScript.Shell)"
                f".CreateShortcut('{_ps_quote(lnk)}'); "
                f"$s.TargetPath = '{_ps_quote(target)}'; $s.Save()"
            )
            return bool(proc and proc.returncode == 0 and lnk.exists())

        if not desk.is_dir():
            return False
        link = desk / target.name
        if link.exists() or link.is_symlink():
            return True  # ya está
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


def pin_to_file_manager(target):
    """Ancla `target` al panel del explorador de archivos.

    Windows: «Acceso rápido» del Explorador (verbo shell 'pintohome').
    Linux: marcadores GTK (~/.config/gtk-3.0/bookmarks), que leen Nautilus,
    Nemo, Thunar y los diálogos de archivo de GTK.
    """
    try:
        target = Path(target)
        if os.name == "nt":
            proc = _powershell(
                f"(New-Object -ComObject shell.application)"
                f".Namespace('{_ps_quote(target)}').Self.InvokeVerb('pintohome')"
            )
            return bool(proc and proc.returncode == 0)

        bookmarks = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
        line = f"{target.as_uri()} {target.name}"
        if bookmarks.exists():
            existing = bookmarks.read_text(encoding="utf-8").splitlines()
            if any(e.split(" ")[0] == target.as_uri() for e in existing if e.strip()):
                return True  # ya está
            content = "\n".join(existing + [line]) + "\n"
        else:
            bookmarks.parent.mkdir(parents=True, exist_ok=True)
            content = line + "\n"
        bookmarks.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False
