import json
import os
import re
import subprocess
import time
import fcntl
import hashlib
from pathlib import Path
import requests

# Detección de idioma para las minutas
try:
    from langdetect import detect
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

# Intentar usar tqdm para la barra de progreso, si no está, sigue sin ella
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# --- CONFIGURACIÓN DE RUTAS ABSOLUTAS ---
BASE_PATH = Path("/home/dax/dev/meet-transcriptions")
AUDIOS_DIR = Path("/home/dax/Audios")
TRANSCRIPTIONS_DIR = AUDIOS_DIR / "transcriptions"
PROCESSED_DIR = AUDIOS_DIR / "procesados"
MINUTAS_DIR = AUDIOS_DIR / "Minutas"
LOG_FILE = AUDIOS_DIR / "done_transcriptions.txt"

# Colores para la terminal
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def load_key(provider):
    key_file = BASE_PATH / f"{provider}.key"
    return key_file.read_text().strip() if key_file.exists() else None


GROQ_API_KEY = load_key("groq")
GLADIA_API_KEY = load_key("gladia")
DEEPGRAM_API_KEY = load_key("deepgram")

# Asegurar que existan las carpetas
for d in [TRANSCRIPTIONS_DIR, PROCESSED_DIR, MINUTAS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def split_audio(file_path):
    """Divide el audio en segmentos de 10 min para evitar límites de tamaño de las APIs."""
    temp_dir = Path(f"/tmp/seg_{os.getpid()}_{int(time.time())}")
    temp_dir.mkdir(exist_ok=True)
    cmd = [
        "ffmpeg", "-i", str(file_path), "-vn", "-f", "segment",
        "-segment_time", "600", "-acodec", "libmp3lame", "-q:a", "2",
        f"{temp_dir}/seg_%03d.mp3", "-y"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    segments = sorted(list(temp_dir.glob("*.mp3")))
    if proc.returncode != 0 or not segments:
        err = proc.stderr.decode("utf-8", errors="replace")[-500:] if proc.stderr else ""
        print(f"{RED}❌ ffmpeg falló (rc={proc.returncode}). stderr:{RESET}\n{err}")
    return segments, temp_dir


def transcribe_with_provider(file_path, provider, diarize=False, offset_sec=0):
    """Intenta transcribir un segmento con un proveedor específico.

    Si diarize=True y el proveedor lo soporta, devuelve una lista de dicts:
        [{"speaker": int, "start": float, "end": float, "text": str}, ...]
    En caso contrario (o si falla la diarización) devuelve el texto plano (str)
    o None si hubo un error total.
    """
    try:
        if provider == "groq":
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    headers=headers,
                    files={"file": f, "model": (None, "whisper-large-v3")},
                    timeout=60,
                )
                if res.status_code == 429:
                    return "RATE_LIMIT"
                return res.json().get("text") if res.status_code == 200 else None

        elif provider == "gladia":
            headers = {"x-gladia-key": GLADIA_API_KEY}

            # Paso 1: subir el audio a /v2/upload
            with open(file_path, "rb") as f:
                up = requests.post(
                    "https://api.gladia.io/v2/upload",
                    headers=headers,
                    files={"audio": f},
                    timeout=120,
                )
            if up.status_code != 200:
                return None
            audio_url = up.json().get("audio_url")
            if not audio_url:
                return None

            # Paso 2: lanzar el job /v2/pre-recorded
            body = {
                "audio_url": audio_url,
                "language_config": {
                    "languages": ["es", "en"],
                    "code_switching": True,
                },
            }
            if diarize:
                body["diarization"] = True

            res = requests.post(
                "https://api.gladia.io/v2/pre-recorded",
                headers={**headers, "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            if res.status_code not in (200, 201):
                return None
            res_url = res.json().get("result_url")
            if not res_url:
                return None

            # Paso 3: poll del resultado (hasta ~6 min para segmentos de 10 min)
            for _ in range(180):
                poll = requests.get(res_url, headers=headers, timeout=30).json()
                status = poll.get("status")
                if status == "done":
                    transcription = poll.get("result", {}).get("transcription", {})
                    if diarize:
                        utterances = transcription.get("utterances", [])
                        if not utterances:
                            return None
                        return [
                            {
                                "speaker": u.get("speaker", 0),
                                "start": round(u["start"] + offset_sec, 3),
                                "end": round(u["end"] + offset_sec, 3),
                                "text": u.get("text", "").strip(),
                            }
                            for u in utterances
                            if u.get("text", "").strip()
                        ]
                    return transcription.get("full_transcript")
                if status == "error":
                    return None
                time.sleep(2)
            return None

        elif provider == "deepgram":
            # language=multi habilita code-switching en nova-3 (ES/EN/PT/etc.),
            # clave para hablantes con acento o que mezclan idiomas.
            if diarize:
                url = (
                    "https://api.deepgram.com/v1/listen"
                    "?smart_format=true&language=multi"
                    "&diarize=true&utterances=true&model=nova-3"
                )
            else:
                url = (
                    "https://api.deepgram.com/v1/listen"
                    "?smart_format=true&language=multi&model=nova-3"
                )
            headers = {
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "audio/mpeg",
            }
            with open(file_path, "rb") as f:
                res = requests.post(url, headers=headers, data=f, timeout=60)

            if res.status_code != 200:
                return None

            data = res.json()
            alternatives = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]

            if diarize:
                utterances = data.get("results", {}).get("utterances", [])
                if utterances:
                    return [
                        {
                            "speaker": u["speaker"],
                            "start": round(u["start"] + offset_sec, 3),
                            "end": round(u["end"] + offset_sec, 3),
                            "text": u["transcript"].strip(),
                        }
                        for u in utterances
                        if u.get("transcript", "").strip()
                    ]
                # Si no hay utterances, devolvemos None para que haga fallback
                return None

            return alternatives.get("transcript")

    except Exception:
        return None
    return None


def fmt_vtt_time(seconds):
    """Convierte segundos a formato WebVTT: hh:mm:ss.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def fmt_txt_time(seconds):
    """Convierte segundos a formato legible: hh:mm:ss"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_diarization_outputs(utterances):
    """Genera contenido VTT, TXT y JSON a partir de una lista de utterances."""
    # --- VTT ---
    vtt_lines = ["WEBVTT", ""]
    for u in utterances:
        start = fmt_vtt_time(u["start"])
        end = fmt_vtt_time(u["end"])
        vtt_lines.append(f"{start} --> {end}")
        vtt_lines.append(f"<v Speaker {u['speaker']}>{u['text']}")
        vtt_lines.append("")

    # --- TXT legible ---
    txt_lines = []
    for u in utterances:
        t = fmt_txt_time(u["start"])
        txt_lines.append(f"[{t}] Speaker {u['speaker']}: {u['text']}")

    # --- JSON estructurado ---
    json_content = json.dumps({"diarized": True, "utterances": utterances}, ensure_ascii=False, indent=2)

    return "\n".join(vtt_lines), "\n".join(txt_lines), json_content


def build_fallback_outputs(segment_texts, segment_duration=600):
    """Genera VTT, TXT y JSON a partir de textos planos de segmentos (sin diarización).
    Usa el índice del segmento para estimar timestamps aproximados."""
    # --- VTT ---
    vtt_lines = ["WEBVTT", ""]
    for idx, text in enumerate(segment_texts):
        start = idx * segment_duration
        end = start + segment_duration
        vtt_lines.append(f"{fmt_vtt_time(start)} --> {fmt_vtt_time(end)}")
        vtt_lines.append(text)
        vtt_lines.append("")

    # --- TXT ---
    txt_lines = []
    for idx, text in enumerate(segment_texts):
        t = fmt_txt_time(idx * segment_duration)
        txt_lines.append(f"[{t}] {text}")

    # --- JSON ---
    segments = [
        {"start": idx * segment_duration, "end": (idx + 1) * segment_duration, "text": text}
        for idx, text in enumerate(segment_texts)
    ]
    json_content = json.dumps({"diarized": False, "segments": segments}, ensure_ascii=False, indent=2)

    return "\n".join(vtt_lines), "\n".join(txt_lines), json_content


# --- Generación de minuta con estrategia map-reduce ---------------------------
# Cada modelo de Groq tiene su propio cupo TPM (tokens por minuto) en el free
# tier. Rotamos entre varios en el paso "map" para repartir la carga y esquivar
# los 429/413 que aparecían al mandar todo el transcript en una sola llamada.
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# Modelos usados para condensar cada trozo (paso map). Se rotan round-robin
# para repartir el TPM. Solo modelos que aguantan un trozo de ~10k chars sin
# 413 en free tier (gpt-oss-20b quedó fuera: TPM demasiado bajo).
MAP_MODELS = [
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "llama-3.3-70b-versatile",
]
# Modelo fuerte para armar la minuta final (paso reduce).
REDUCE_MODEL = "llama-3.3-70b-versatile"

# Presupuesto de caracteres por trozo. En español ~2.6 chars/token, así que
# 10k chars ≈ 3.8k tokens: entra incluso en los modelos de TPM más bajo del
# free tier (p.ej. qwen3-32b, con 6000 TPM) sumando prompt y salida.
MAP_CHUNK_CHARS = 10000


def _detect_lang(text):
    """Detecta el idioma del texto de forma programática (default 'en')."""
    if HAS_LANGDETECT and text:
        try:
            return detect(text[:2000])
        except Exception:
            pass
    return "en"


def _parse_retry_after(res):
    """Segundos a esperar ante un 429, según el header o el cuerpo de Groq."""
    ra = res.headers.get("retry-after")
    if ra:
        try:
            return float(ra) + 0.5
        except ValueError:
            pass
    m = re.search(r"try again in ([0-9.]+)s", res.text)
    if m:
        return float(m.group(1)) + 0.5
    return 8.0


def _groq_chat(messages, model, max_tokens=1200, temperature=0.3, max_retries=4):
    """Llama al chat de Groq con reintentos/backoff ante 429.

    Devuelve el texto de la respuesta, o None si falla tras los reintentos
    (o ante un error no recuperable como 413).
    """
    if not GROQ_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(max_retries):
        try:
            res = requests.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=180)
        except Exception as e:
            print(f"{RED}❌ Groq LLM excepción ({model}): {e}{RESET}")
            time.sleep(2 * (attempt + 1))
            continue
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
        if res.status_code == 429:
            wait = _parse_retry_after(res)
            print(f"{YELLOW}⏳ 429 en {model}, reintento en {wait:.1f}s{RESET}")
            time.sleep(wait)
            continue
        # 413 u otros: reintentar el mismo request no ayuda.
        print(f"{RED}❌ Groq LLM error {res.status_code} ({model}): {res.text[:200]}{RESET}")
        return None
    return None


def _chunk_text(text, size):
    """Parte el texto en trozos <= size, cortando por salto de línea/espacio."""
    chunks = []
    remaining = text
    while len(remaining) > size:
        cut = remaining.rfind("\n", 0, size)
        if cut < size * 0.5:  # sin salto útil: cortar por espacio
            cut = remaining.rfind(" ", 0, size)
        if cut <= 0:
            cut = size
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining.strip():
        chunks.append(remaining)
    return chunks


def _map_condense(text, lang):
    """MAP: condensa cada trozo del texto, rotando modelos para repartir el TPM."""
    chunks = _chunk_text(text, MAP_CHUNK_CHARS)
    out = []
    for i, chunk in enumerate(chunks):
        model = MAP_MODELS[i % len(MAP_MODELS)]
        sys_msg = (
            "You condense meeting-transcript fragments. Produce a dense but "
            "faithful summary preserving decisions, action items, names, numbers "
            "and key points. Do not invent content."
        )
        usr_msg = (
            f"Fragment {i + 1} of {len(chunks)} of a meeting transcript "
            f"(language '{lang}'). Summarize it in that SAME language, keeping "
            f"every decision, task, owner, date and figure:\n\n{chunk}"
        )
        summary = _groq_chat(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": usr_msg}],
            model=model, max_tokens=1200,
        )
        if summary:
            out.append(f"[Parte {i + 1}]\n{summary}")
            print(f"   ✅ trozo {i + 1}/{len(chunks)} condensado ({model})")
        else:
            # Si falla el resumen, incluir el crudo recortado para no perder info.
            out.append(f"[Parte {i + 1} — sin resumir]\n{chunk[:4000]}")
            print(f"{YELLOW}   ⚠️  trozo {i + 1}/{len(chunks)} sin resumir ({model}){RESET}")
        time.sleep(1)  # pequeño respiro para el TPM
    return "\n\n".join(out)


def _build_minuta(content, filename, lang, model, from_summaries=False):
    """REDUCE / pasada única: arma la minuta final en Markdown."""
    system_msg = (
        "You are an expert assistant at writing clear, concise, and "
        "professional meeting minutes. Extract only relevant information: "
        "executive summary, topics discussed, decisions, action items, and participants."
    )
    source_desc = (
        "the following per-section summaries of a meeting transcript"
        if from_summaries else "the following transcript"
    )
    user_msg = (
        f"Generate professional meeting minutes in Markdown from {source_desc}. "
        f"The original file is named '{filename}'.\n\n"
        f"CRITICAL: The content is in language '{lang}'. "
        f"Write the ENTIRE output (including all section titles) in language '{lang}'. "
        f"Do NOT use any other language.\n\n"
        "Required format:\n"
        "# Meeting Minutes: [file name]\n\n"
        "## Executive Summary\n"
        "2-3 paragraphs summarizing the meeting.\n\n"
        "## Participants\n"
        "List of people who spoke (if speakers or names are identified). "
        "If none are identified, write 'Not identified' in the required language.\n\n"
        "## Topics Discussed\n"
        "- Main topic 1\n"
        "- Main topic 2\n"
        "- ...\n\n"
        "## Decisions and Agreements\n"
        "- Decision/agreement 1\n"
        "- ...\n\n"
        "## Action Items\n"
        "| Owner | Action | Due Date (if mentioned) |\n"
        "|-------|--------|-------------------------|\n"
        "| ... | ... | ... |\n\n"
        "## Additional Key Points\n"
        "- Relevant point 1\n"
        "- ...\n\n"
        "---\n"
        f"Content:\n{content}"
    )
    return _groq_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        model=model, max_tokens=4096,
    )


def generate_minuta(transcript_text, filename):
    """Genera una minuta en Markdown desde el transcript, usando map-reduce.

    1) MAP: parte el transcript en trozos y condensa cada uno con un LLM,
       rotando entre varios modelos para repartir el cupo TPM del free tier.
    2) REDUCE: junta los resúmenes (mucho más chicos) y arma la minuta final
       en una sola llamada a un modelo fuerte; si los resúmenes siguen siendo
       grandes, condensa de nuevo (reduce jerárquico).
    Para transcripts cortos hace una sola pasada directa.
    """
    if not GROQ_API_KEY or not transcript_text.strip():
        return None

    detected_lang = _detect_lang(transcript_text)
    chunks = _chunk_text(transcript_text, MAP_CHUNK_CHARS)

    if len(chunks) == 1:
        # Cabe en una sola llamada: minuta directa.
        return _build_minuta(transcript_text, filename, detected_lang, REDUCE_MODEL)

    print(f"{YELLOW}🧩 Transcript largo: {len(chunks)} trozos, condensando…{RESET}")
    merged = _map_condense(transcript_text, detected_lang)

    # Si los resúmenes juntos siguen sin caber, condensarlos otra vez.
    guard = 0
    while len(merged) > MAP_CHUNK_CHARS and guard < 3:
        print(f"{YELLOW}🔁 Resúmenes aún grandes ({len(merged)} chars), condensando de nuevo…{RESET}")
        merged = _map_condense(merged, detected_lang)
        guard += 1

    return _build_minuta(merged, filename, detected_lang, REDUCE_MODEL, from_summaries=True)


def process_file(file_path):
    print(f"\n{YELLOW}📂 Procesando:{RESET} {file_path.name}")

    segments, temp_dir = split_audio(file_path)
    if not segments:
        print(
            f"{RED}🚫 No se generaron segmentos. Abortando este archivo "
            f"(NO se mueve a procesados).{RESET}"
        )
        try:
            temp_dir.rmdir()
        except OSError:
            pass
        return

    providers = [
        ("groq", GROQ_API_KEY),
        ("gladia", GLADIA_API_KEY),
        ("deepgram", DEEPGRAM_API_KEY),
    ]

    if HAS_TQDM:
        pbar = tqdm(total=len(segments), desc="Progreso", unit="seg")

    # ------------------------------------------------------------------
    # 1) Intentar diarización para TODOS los segmentos, probando proveedores en orden
    # ------------------------------------------------------------------
    diarization_providers = []
    if DEEPGRAM_API_KEY:
        diarization_providers.append("deepgram")
    if GLADIA_API_KEY:
        diarization_providers.append("gladia")

    all_utterances = []
    diarization_ok = bool(diarization_providers)

    if diarization_ok:
        for idx, seg in enumerate(segments):
            offset = idx * 600
            segment_utterances = None
            for p_name in diarization_providers:
                result = transcribe_with_provider(seg, p_name, diarize=True, offset_sec=offset)
                if isinstance(result, list) and result:
                    segment_utterances = result
                    break
                print(
                    f"\n{YELLOW}⚠️ Diarización con {p_name.upper()} falló en "
                    f"segmento {idx + 1}/{len(segments)}.{RESET}"
                )

            if segment_utterances is not None:
                all_utterances.extend(segment_utterances)
                if HAS_TQDM:
                    pbar.update(1)
            else:
                diarization_ok = False
                if HAS_TQDM:
                    pbar.n = 0  # reset barra para re-procesar
                break

    # ------------------------------------------------------------------
    # 2) Si la diarización falló en algún segmento, caemos a texto plano
    # ------------------------------------------------------------------
    if not diarization_ok:
        all_utterances = []
        full_transcript = []
        overall_success = True

        for seg in segments:
            segment_text = None
            for p_name, p_key in providers:
                if not p_key:
                    continue

                result = transcribe_with_provider(seg, p_name)

                if result == "RATE_LIMIT":
                    print(
                        f"\n{RED}⚠️ {p_name.upper()} alcanzó el límite.{RESET} "
                        f"Probando siguiente..."
                    )
                    continue
                elif result:
                    segment_text = result
                    break
                else:
                    print(f"\n{RED}❌ {p_name.upper()} falló.{RESET}")

            if segment_text:
                full_transcript.append(segment_text)
                if HAS_TQDM:
                    pbar.update(1)
            else:
                overall_success = False
                break

        if HAS_TQDM:
            pbar.close()

        if overall_success:
            vtt_content, txt_content, json_content = build_fallback_outputs(full_transcript)
            out_vtt = TRANSCRIPTIONS_DIR / f"{file_path.stem}.vtt"
            out_txt = TRANSCRIPTIONS_DIR / f"{file_path.stem}.txt"
            out_json = TRANSCRIPTIONS_DIR / f"{file_path.stem}.json"
            out_vtt.write_text(vtt_content, encoding="utf-8")
            out_txt.write_text(txt_content, encoding="utf-8")
            out_json.write_text(json_content, encoding="utf-8")
            os.rename(file_path, PROCESSED_DIR / file_path.name)
            minuta = generate_minuta(txt_content, file_path.name)
            out_md = MINUTAS_DIR / f"{file_path.stem}.md"
            if minuta:
                out_md.write_text(minuta, encoding="utf-8")
            else:
                out_md.touch()
            with open(LOG_FILE, "a") as log:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                log.write(f"{file_path.name} | {ts}\n")
            print(
                f"{GREEN}✅ Transcripción completada (sin diarización).{RESET}\n"
                f"   VTT  → {out_vtt.name}\n"
                f"   TXT  → {out_txt.name}\n"
                f"   JSON → {out_json.name}\n"
                f"   MD   → {out_md.name} ({'con minuta' if minuta else 'vacío'})"
            )
        else:
            print(
                f"{RED}🚫 No se pudo procesar el archivo con ninguna IA disponible.{RESET}"
            )

        # Limpieza
        for f in segments:
            f.unlink()
        temp_dir.rmdir()
        return

    # ------------------------------------------------------------------
    # 3) Diarización exitosa: generar VTT + TXT
    # ------------------------------------------------------------------
    if HAS_TQDM:
        pbar.close()

    vtt_content, txt_content, json_content = build_diarization_outputs(all_utterances)

    out_vtt = TRANSCRIPTIONS_DIR / f"{file_path.stem}.vtt"
    out_txt = TRANSCRIPTIONS_DIR / f"{file_path.stem}.txt"
    out_json = TRANSCRIPTIONS_DIR / f"{file_path.stem}.json"
    out_vtt.write_text(vtt_content, encoding="utf-8")
    out_txt.write_text(txt_content, encoding="utf-8")
    out_json.write_text(json_content, encoding="utf-8")

    os.rename(file_path, PROCESSED_DIR / file_path.name)
    minuta = generate_minuta(txt_content, file_path.name)
    out_md = MINUTAS_DIR / f"{file_path.stem}.md"
    if minuta:
        out_md.write_text(minuta, encoding="utf-8")
    else:
        out_md.touch()
    with open(LOG_FILE, "a") as log:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"{file_path.name} | {ts}\n")

    print(
        f"{GREEN}✅ Transcripción con diarización completada.{RESET}\n"
        f"   VTT  → {out_vtt.name}\n"
        f"   TXT  → {out_txt.name}\n"
        f"   JSON → {out_json.name}\n"
        f"   MD   → {out_md.name} ({'con minuta' if minuta else 'vacío'})"
    )

    # Limpieza
    for f in segments:
        f.unlink()
    temp_dir.rmdir()


LOCK_DIR = Path("/tmp/transcripcion_locks")
LOCK_DIR.mkdir(exist_ok=True)


def try_lock(file_path):
    """Intenta tomar un lock exclusivo no-bloqueante para `file_path`.
    Devuelve el file descriptor del lock si tuvo éxito, o None si otra instancia lo tiene.
    Usar hash del path absoluto para evitar colisiones por nombres con caracteres raros."""
    h = hashlib.sha1(str(file_path.resolve()).encode()).hexdigest()[:16]
    lock_path = LOCK_DIR / f"{h}.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    # Escribir el PID dentro del lock para diagnóstico
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def release_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


if __name__ == "__main__":
    if not LOG_FILE.exists():
        LOG_FILE.touch()
    processed = set()
    for line in LOG_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Formato nuevo: "nombre_archivo | YYYY-MM-DD HH:MM:SS"
        # Formato viejo: "nombre_archivo"
        processed.add(stripped.split("|")[0].strip())

    valid_ext = [".mp3", ".wav", ".m4a", ".mkv", ".mp4", ".ogg"]
    to_process = [
        f
        for f in AUDIOS_DIR.glob("*")
        if f.suffix.lower() in valid_ext and f.name not in processed
    ]

    if not to_process:
        print(f"{GREEN}Sin archivos nuevos.{RESET}")
    else:
        worked = False
        for f in to_process:
            # Re-chequear: otro proceso pudo haber terminado y movido el archivo a procesados/
            if not f.exists():
                continue
            lock_fd = try_lock(f)
            if lock_fd is None:
                # Otra instancia ya está procesando este archivo: pasar al siguiente
                print(
                    f"{YELLOW}⏭  {f.name}: ocupado por otra instancia, "
                    f"paso al siguiente.{RESET}"
                )
                continue
            try:
                worked = True
                process_file(f)
            finally:
                release_lock(lock_fd)
            # Solo procesamos UN archivo por instancia: si esta instancia tomó f,
            # otras instancias paralelas pueden estar trabajando con f2, f3, etc.
            break
        if not worked:
            print(
                f"{GREEN}Todos los archivos pendientes están siendo procesados "
                f"por otras instancias.{RESET}"
            )
