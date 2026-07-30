"""Detección y descarga de ffmpeg.

ffmpeg NO se distribuye con la aplicación: en el primer arranque se detecta
si ya está instalado (PATH o ruta configurada) y, si falta, se le ofrece al
usuario descargarlo a un directorio propio de la app (builds estáticos
oficiales de terceros: gyan.dev en Windows, johnvansickle.com en Linux).
"""

import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

from .config import DATA_DIR

BIN_DIR = DATA_DIR / "bin"

WINDOWS_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LINUX_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"

# En la app empaquetada como GUI de Windows no queremos que cada llamada a
# ffmpeg abra una ventana de consola.
SUBPROCESS_FLAGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)

_EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def _works(path):
    try:
        proc = subprocess.run(
            [str(path), "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            **SUBPROCESS_FLAGS,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_ffmpeg(cfg=None):
    """Devuelve la ruta a un ffmpeg utilizable, o None si no hay ninguno.

    Orden: ruta configurada por el usuario → binario descargado por la app →
    lo que haya en el PATH.
    """
    if cfg and cfg.ffmpeg_path:
        p = Path(cfg.ffmpeg_path).expanduser()
        if p.exists() and _works(p):
            return str(p)

    own = BIN_DIR / _EXE
    if own.exists() and _works(own):
        return str(own)

    in_path = shutil.which("ffmpeg")
    if in_path and _works(in_path):
        return in_path

    return None


def download_url():
    if os.name == "nt":
        return WINDOWS_URL
    if platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64"):
        return LINUX_URL
    return None


def download_ffmpeg(progress_cb=None):
    """Descarga ffmpeg y lo instala en BIN_DIR. Devuelve la ruta al binario.

    progress_cb(bytes_descargados, bytes_totales) se llama durante la descarga
    (bytes_totales puede ser 0 si el servidor no lo informa).

    Lanza RuntimeError con un mensaje legible si algo falla o la plataforma
    no tiene build automática (p.ej. Linux ARM: instalar con el gestor de
    paquetes del sistema).
    """
    url = download_url()
    if not url:
        raise RuntimeError(
            "No hay descarga automática para esta plataforma. "
            "Instalá ffmpeg con el gestor de paquetes del sistema "
            "(p.ej. `sudo apt install ffmpeg`)."
        )

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if url.endswith(".zip") else ".tar.xz"

    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
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

        target = BIN_DIR / _EXE
        if suffix == ".zip":
            _extract_from_zip(tmp, target)
        else:
            _extract_from_tar(tmp, target)

        if os.name != "nt":
            target.chmod(0o755)
        if not _works(target):
            raise RuntimeError("El ffmpeg descargado no ejecuta correctamente.")
        return str(target)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _extract_from_zip(archive, target):
    with zipfile.ZipFile(archive) as z:
        member = next(
            (n for n in z.namelist() if n.endswith("bin/ffmpeg.exe")), None
        )
        if not member:
            raise RuntimeError("El zip descargado no contiene ffmpeg.exe.")
        with z.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _extract_from_tar(archive, target):
    with tarfile.open(archive, "r:xz") as t:
        member = next(
            (m for m in t.getmembers()
             if m.isfile() and Path(m.name).name == "ffmpeg"),
            None,
        )
        if not member:
            raise RuntimeError("El tar descargado no contiene el binario ffmpeg.")
        src = t.extractfile(member)
        with open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
