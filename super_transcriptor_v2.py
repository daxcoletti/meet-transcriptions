import os
import subprocess
import time
import fcntl
import hashlib
from pathlib import Path
import requests

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
for d in [TRANSCRIPTIONS_DIR, PROCESSED_DIR]: d.mkdir(parents=True, exist_ok=True)

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

def transcribe_with_provider(file_path, provider):
    """Intenta transcribir un segmento con un proveedor específico."""
    try:
        if provider == "groq":
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            with open(file_path, "rb") as f:
                res = requests.post(url, headers=headers, files={"file": f, "model": (None, "whisper-large-v3")}, timeout=60)
                if res.status_code == 429: return "RATE_LIMIT"
                return res.json().get("text") if res.status_code == 200 else None

        elif provider == "gladia":
            headers = {"x-gladia-key": GLADIA_API_KEY}
            with open(file_path, "rb") as f:
                res = requests.post("https://api.gladia.io/v2/transcription", headers=headers, files={"audio": f}, timeout=60)
                if res.status_code != 201: return None
                res_url = res.json()["result_url"]
                # Poll para esperar el resultado
                for _ in range(60): 
                    poll = requests.get(res_url, headers=headers).json()
                    if poll["status"] == "done": return poll["transcription"]["full_transcript"]
                    if poll["status"] == "error": return None
                    time.sleep(2)

        elif provider == "deepgram":
            url = "https://api.deepgram.com/v1/listen?smart_format=true&language=es"
            headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "audio/mpeg"}
            with open(file_path, "rb") as f:
                res = requests.post(url, headers=headers, data=f, timeout=60)
                return res.json()["results"]["channels"][0]["alternatives"][0]["transcript"] if res.status_code == 200 else None

    except Exception:
        return None
    return None

def process_file(file_path):
    print(f"\n{YELLOW}📂 Procesando:{RESET} {file_path.name}")
    
    segments, temp_dir = split_audio(file_path)
    if not segments:
        print(f"{RED}🚫 No se generaron segmentos. Abortando este archivo (NO se mueve a procesados).{RESET}")
        try: temp_dir.rmdir()
        except OSError: pass
        return

    full_transcript = []
    providers = [("groq", GROQ_API_KEY), ("gladia", GLADIA_API_KEY), ("deepgram", DEEPGRAM_API_KEY)]

    if HAS_TQDM:
        pbar = tqdm(total=len(segments), desc="Progreso", unit="seg")

    overall_success = True
    for seg in segments:
        segment_text = None
        for p_name, p_key in providers:
            if not p_key: continue
            
            result = transcribe_with_provider(seg, p_name)
            
            if result == "RATE_LIMIT":
                print(f"\n{RED}⚠️ {p_name.upper()} alcanzó el límite.{RESET} Probando siguiente...")
                continue
            elif result:
                segment_text = result
                break
            else:
                print(f"\n{RED}❌ {p_name.upper()} falló.{RESET}")

        if segment_text:
            full_transcript.append(segment_text)
            if HAS_TQDM: pbar.update(1)
        else:
            overall_success = False
            break
            
    if HAS_TQDM: pbar.close()

    if overall_success:
        out_vtt = TRANSCRIPTIONS_DIR / f"{file_path.stem}.vtt"
        out_vtt.write_text("WEBVTT\n\n" + "\n".join(full_transcript))
        # Mover original para no repetir
        os.rename(file_path, PROCESSED_DIR / file_path.name)
        with open(LOG_FILE, "a") as log: log.write(f"{file_path.name}\n")
        print(f"{GREEN}✅ Transcripción completada.{RESET}")
    else:
        print(f"{RED}🚫 No se pudo procesar el archivo con ninguna IA disponible.{RESET}")

    # Limpieza
    for f in segments: f.unlink()
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
    if not LOG_FILE.exists(): LOG_FILE.touch()
    processed = set(LOG_FILE.read_text().splitlines())

    valid_ext = [".mp3", ".wav", ".m4a", ".mkv", ".mp4", ".ogg"]
    to_process = [f for f in AUDIOS_DIR.glob("*") if f.suffix.lower() in valid_ext and f.name not in processed]

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
                print(f"{YELLOW}⏭  {f.name}: ocupado por otra instancia, paso al siguiente.{RESET}")
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
            print(f"{GREEN}Todos los archivos pendientes están siendo procesados por otras instancias.{RESET}")
