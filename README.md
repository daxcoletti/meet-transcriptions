# meet-transcriptions

Transcriptor automático de grabaciones de reuniones (Google Meet, Zoom, etc.) que rota entre varias APIs gratuitas para esquivar los límites de cuota individuales, genera transcripción con diarización (identificación de hablantes) y una **minuta** en Markdown.

## Cómo funciona

1. Escanea un directorio de audios (`/home/dax/Audios` por defecto).
2. Por cada archivo nuevo, extrae el audio con `ffmpeg` y lo divide en segmentos de 10 minutos (límite típico de las APIs gratuitas).
3. **Transcripción con diarización**: intenta cada segmento con **Deepgram** (`nova-3`) y, si falla, **Gladia**. Devuelve *utterances* con hablante y timestamps.
4. **Fallback sin diarización**: si ningún proveedor de diarización está disponible o falla, cae a texto plano probando en orden **Groq** (`whisper-large-v3`) → **Gladia** → **Deepgram**. Ante un `429 (rate limit)` salta al siguiente.
5. Une los segmentos y escribe la salida en `transcriptions/`:
   - `.vtt` (WebVTT, con hablantes si hubo diarización)
   - `.txt` (texto plano con timestamps)
   - `.json` (estructura completa: utterances o segmentos)
6. Genera una **minuta** en Markdown en `Minutas/` (ver abajo).
7. Mueve el original a `procesados/` y registra el nombre en `done_transcriptions.txt` para no repetir.

### Minuta con estrategia map-reduce

La minuta se genera con los modelos de chat de **Groq**. Como el free tier tiene un límite de **tokens por minuto (TPM)** bajo (p.ej. 12.000 para `llama-3.3-70b-versatile`), mandar el transcript completo en una sola llamada fallaba con `413 Request too large` en cualquier reunión de más de ~30 min. Para resolverlo se usa **map-reduce**:

- **MAP**: el transcript se parte en trozos (~10k chars) y cada uno se condensa con un LLM, **rotando entre varios modelos** (`gpt-oss-120b`, `llama-4-scout`, `qwen3-32b`, `llama-3.3-70b`) para repartir el cupo TPM (cada modelo tiene su propio límite). Los `429` se reintentan respetando el `retry-after`.
- **REDUCE**: se juntan los resúmenes (mucho más chicos) y se arma la minuta final en una sola llamada a un modelo fuerte. Si los resúmenes juntos todavía no entran, se condensan de nuevo (reduce jerárquico).
- Transcripts cortos → una sola pasada directa.

El idioma de la minuta se detecta automáticamente con `langdetect`.

### Diseño para correr por cron

El script se ejecuta cada minuto vía cron. Para evitar que dos instancias procesen el mismo archivo (gastando cuota gratuita 2×) usa **locks por archivo** con `fcntl.flock`:

- Cada instancia toma **un único archivo**, lo procesa y termina.
- Si hay un segundo archivo, la siguiente instancia (el próximo minuto, o una en paralelo) lo toma sin pisar el primero.
- Los locks viven en `/tmp/transcripcion_locks/<sha1>.lock` y se liberan al terminar (o al morir el proceso, por el comportamiento de `flock`).

## Requisitos

- Linux con `ffmpeg` instalado (`apt install ffmpeg`)
- Python 3.10+
- Cuentas gratuitas en al menos uno de:
  - [Groq](https://console.groq.com/) (transcripción Whisper + LLM para la minuta)
  - [Gladia](https://www.gladia.io/) (transcripción + diarización)
  - [Deepgram](https://console.deepgram.com/) (transcripción + diarización)

## Instalación

```bash
git clone git@github.com:daxcoletti/meet-transcriptions.git
cd meet-transcriptions

python3 -m venv venv
source venv/bin/activate
pip install requests tqdm langdetect
```

## Configuración

1. **API keys**: cada proveedor lee su key desde un archivo en la raíz del repo (que está en `.gitignore`):

   ```bash
   echo "tu-groq-api-key"     > groq.key
   echo "tu-gladia-api-key"   > gladia.key
   echo "tu-deepgram-api-key" > deepgram.key
   ```

   Solo hace falta tener al menos uno; los faltantes se omiten automáticamente. La minuta requiere `groq.key`. La diarización requiere `deepgram.key` o `gladia.key`.

2. **Rutas** (editar al inicio de `super_transcriptor_v2.py` si querés otras):

   ```python
   AUDIOS_DIR          = Path("/home/dax/Audios")
   TRANSCRIPTIONS_DIR  = AUDIOS_DIR / "transcriptions"
   PROCESSED_DIR       = AUDIOS_DIR / "procesados"
   MINUTAS_DIR         = AUDIOS_DIR / "Minutas"
   LOG_FILE            = AUDIOS_DIR / "done_transcriptions.txt"
   ```

   Las carpetas y el log se crean solos en la primera corrida.

## Uso manual

```bash
source venv/bin/activate
python super_transcriptor_v2.py
```

Procesa **un** archivo y termina (por diseño, para que múltiples instancias paralelas tomen distintos archivos).

## Uso por cron (recomendado)

`run_transcription.sh` activa el venv y ejecuta el script. Agregarlo al cron (la redirección del log la maneja quien invoca):

```cron
* * * * * dax /home/dax/dev/meet-transcriptions/run_transcription.sh >> /home/dax/Audios/cron.log 2>&1
```

Con esto, cron lanza una instancia por minuto. Si todavía está corriendo la anterior, la nueva tomará el siguiente archivo libre o terminará silenciosamente diciendo que no hay nada por hacer.

## Salida

Para `Reunion 2026-04-28.mkv` se genera:

- `transcriptions/Reunion 2026-04-28.vtt` — WebVTT (con hablantes si hubo diarización)
- `transcriptions/Reunion 2026-04-28.txt` — texto plano con timestamps
- `transcriptions/Reunion 2026-04-28.json` — estructura completa
- `Minutas/Reunion 2026-04-28.md` — minuta en Markdown (vacío si no hay `groq.key` o falla el LLM)
- el archivo original se mueve a `procesados/`
- el nombre queda registrado en `done_transcriptions.txt`

## Errores comunes

- **`ffmpeg: not found`** → instalar con `apt install ffmpeg`.
- **La minuta sale vacía en reuniones largas** → era el bug de `413 Request too large` por el límite TPM; resuelto con el map-reduce (ver arriba). Verificar que `langdetect` esté instalado y que `groq.key` sea válida.
- **Cron no encuentra `python`** → usar `run_transcription.sh` que activa el venv, o poner la ruta absoluta al python del venv en el crontab.

## Licencia

Uso personal.
