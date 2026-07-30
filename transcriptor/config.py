"""Configuración persistente multiplataforma.

Todo vive en un `config.json` dentro del directorio estándar de configuración
del usuario (Linux: ~/.config/MeetTranscriptions, Windows:
%APPDATA%\\MeetTranscriptions). Las API keys se guardan ahí.

Compatibilidad con el esquema viejo: si no hay config.json pero existen
archivos `<proveedor>.key` en la raíz del repo, se usan esas keys (así el
cron existente sigue funcionando sin tocar nada).

Para tests se puede redirigir todo con la variable de entorno
MEET_TRANSCRIPTIONS_CONFIG_DIR.
"""

import json
import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "MeetTranscriptions"

_env_dir = os.environ.get("MEET_TRANSCRIPTIONS_CONFIG_DIR")
if _env_dir:
    CONFIG_DIR = Path(_env_dir)
    DATA_DIR = Path(_env_dir) / "data"
else:
    CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
    DATA_DIR = Path(user_data_dir(APP_NAME, appauthor=False))

CONFIG_FILE = CONFIG_DIR / "config.json"

# Orden de fallback para transcripción sin diarización.
TRANSCRIPTION_PROVIDERS = [
    "groq", "gladia", "deepgram", "assemblyai", "elevenlabs", "speechmatics",
]
# Proveedores que soportan diarización, en orden de preferencia.
DIARIZATION_PROVIDERS = [
    "deepgram", "gladia", "assemblyai", "elevenlabs", "speechmatics",
]
ALL_PROVIDERS = TRANSCRIPTION_PROVIDERS + ["gemini"]

VALID_EXTENSIONS = [".mp3", ".wav", ".m4a", ".mkv", ".mp4", ".ogg"]

_DEFAULTS = {
    "audios_dir": str(Path.home() / "Audios"),
    "api_keys": {},
    "speechmatics_lang": "en",
    "ffmpeg_path": "",  # vacío = autodetectar (PATH o descarga propia)
}


class Config:
    def __init__(self, data=None):
        self.data = {**_DEFAULTS, **(data or {})}
        # Descartar keys vacías para que los chequeos `if key` funcionen.
        self.data["api_keys"] = {
            k: v.strip() for k, v in (self.data.get("api_keys") or {}).items()
            if v and v.strip()
        }

    # --- Rutas derivadas (misma estructura que siempre) ---
    @property
    def audios_dir(self):
        return Path(self.data["audios_dir"]).expanduser()

    @property
    def transcriptions_dir(self):
        return self.audios_dir / "transcriptions"

    @property
    def processed_dir(self):
        return self.audios_dir / "procesados"

    @property
    def minutas_dir(self):
        return self.audios_dir / "Minutas"

    @property
    def progress_dir(self):
        return self.audios_dir / "progress"

    @property
    def log_file(self):
        return self.audios_dir / "done_transcriptions.txt"

    # --- Accesos simples ---
    @property
    def api_keys(self):
        return self.data["api_keys"]

    def get_key(self, provider):
        return self.data["api_keys"].get(provider)

    @property
    def speechmatics_lang(self):
        return self.data.get("speechmatics_lang", "en")

    @property
    def ffmpeg_path(self):
        return self.data.get("ffmpeg_path", "")

    def has_transcription_key(self):
        return any(self.get_key(p) for p in TRANSCRIPTION_PROVIDERS)

    def ensure_dirs(self):
        for d in [self.audios_dir, self.transcriptions_dir,
                  self.processed_dir, self.minutas_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, CONFIG_FILE)


def is_first_run():
    return not CONFIG_FILE.exists()


def _legacy_data():
    """Keys en archivos `<proveedor>.key` en la raíz del repo (esquema viejo)."""
    repo = Path(__file__).resolve().parent.parent
    keys = {}
    for p in ALL_PROVIDERS:
        f = repo / f"{p}.key"
        if f.exists():
            keys[p] = f.read_text().strip()
    return {"api_keys": keys} if keys else {}


def load():
    if CONFIG_FILE.exists():
        try:
            return Config(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return Config(_legacy_data())
