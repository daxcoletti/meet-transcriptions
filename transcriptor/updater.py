"""Detección y aplicación de actualizaciones vía GitHub Releases.

- check_latest() consulta el último release publicado y lo compara con la
  versión local.
- En Windows empaquetado (Inno Setup), la actualización se aplica previa
  confirmación del usuario: se descarga el Setup nuevo y se ejecuta con
  /SILENT (muestra la ventana de progreso, sin páginas de wizard); el
  instalador cierra la app (CloseApplications=force), reemplaza los
  archivos y la vuelve a abrir ([Run] postinstall sin skipifsilent).
- Corriendo desde código (Linux/dev) solo se notifica y se abre la página
  del release.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from . import __version__

REPO = "daxcoletti/meet-transcriptions"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(v):
    """'v2.10.3' → (2, 10, 3); tolera sufijos no numéricos."""
    parts = []
    for p in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_latest(timeout=15):
    """Devuelve info del release más nuevo que la versión local, o None.

    {"version": "2.3.0", "installer_url": ..., "page_url": ...}
    Lanza requests.RequestException si no se pudo consultar.
    """
    res = requests.get(
        API_LATEST,
        timeout=timeout,
        headers={"Accept": "application/vnd.github+json"},
    )
    res.raise_for_status()
    data = res.json()
    tag = data.get("tag_name") or ""
    if not tag or parse_version(tag) <= parse_version(__version__):
        return None
    asset = next(
        (a for a in data.get("assets", [])
         if a.get("name", "").lower().endswith(".exe")),
        None,
    )
    return {
        "version": tag.lstrip("vV"),
        "installer_url": asset.get("browser_download_url") if asset else None,
        "page_url": data.get("html_url") or f"https://github.com/{REPO}/releases",
    }


def can_self_update():
    """Solo la app empaquetada de Windows puede auto-actualizarse."""
    return os.name == "nt" and getattr(sys, "frozen", False)


def download_installer(url, progress_cb=None):
    """Descarga el Setup a un archivo temporal y devuelve su ruta."""
    fd, tmp_name = tempfile.mkstemp(prefix="MeetTranscriptions-Update-", suffix=".exe")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            with requests.get(url, stream=True, timeout=60) as res:
                res.raise_for_status()
                total = int(res.headers.get("content-length") or 0)
                done = 0
                for chunk in res.iter_content(chunk_size=1024 * 256):
                    out.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(done, total)
        return tmp
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def launch_installer(path):
    """Lanza el Setup desacoplado de este proceso.

    /SILENT (una sola barra de progreso visible, sin wizard) y no
    /VERYSILENT: el usuario ya confirmó en la app, pero tiene que VER que
    la actualización está ocurriendo.

    Quien llama debe cerrar la app inmediatamente después: el instalador
    reemplaza los archivos y la vuelve a abrir solo.
    """
    flags = {}
    if os.name == "nt":
        # Que sobreviva al cierre de la app.
        flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(path), "/SILENT", "/NORESTART"],
        close_fds=True,
        **flags,
    )
