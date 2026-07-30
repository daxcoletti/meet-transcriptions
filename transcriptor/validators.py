"""Validación liviana de API keys: una llamada barata por proveedor.

check_key devuelve (ok, mensaje):
  ok = True   → la key funciona
  ok = False  → la key fue rechazada (401/403)
  ok = None   → no se pudo determinar (red caída, endpoint raro, etc.)
"""

import requests

_CHECKS = {
    "groq": lambda k: requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {k}"}, timeout=15,
    ),
    "gladia": lambda k: requests.get(
        "https://api.gladia.io/v2/pre-recorded?limit=1",
        headers={"x-gladia-key": k}, timeout=15,
    ),
    "deepgram": lambda k: requests.get(
        "https://api.deepgram.com/v1/auth/token",
        headers={"Authorization": f"Token {k}"}, timeout=15,
    ),
    "assemblyai": lambda k: requests.get(
        "https://api.assemblyai.com/v2/transcript?limit=1",
        headers={"authorization": k}, timeout=15,
    ),
    "elevenlabs": lambda k: requests.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": k}, timeout=15,
    ),
    "speechmatics": lambda k: requests.get(
        "https://asr.api.speechmatics.com/v2/jobs?limit=1",
        headers={"Authorization": f"Bearer {k}"}, timeout=15,
    ),
    "gemini": lambda k: requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
        headers={"x-goog-api-key": k}, timeout=15,
    ),
}


def check_key(provider, key):
    fn = _CHECKS.get(provider)
    if fn is None or not key:
        return None, "Sin verificación disponible"
    try:
        res = fn(key.strip())
    except requests.RequestException as e:
        return None, f"No se pudo verificar (red): {e.__class__.__name__}"
    if res.status_code == 200:
        return True, "Key válida"
    if res.status_code in (401, 403):
        return False, f"Key rechazada ({res.status_code})"
    # Gemini responde 400 ante keys malformadas.
    if provider == "gemini" and res.status_code == 400:
        return False, "Key rechazada (400)"
    return None, f"Respuesta inesperada ({res.status_code})"
