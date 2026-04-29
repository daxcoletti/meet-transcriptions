# meet-transcriptions

Transcriptor automático de grabaciones de reuniones (Google Meet, Zoom, etc.) que rota entre varias APIs gratuitas para esquivar los límites de cuota individuales.

## Cómo funciona

1. Escanea un directorio de audios (`/home/dax/Audios` por defecto).
2. Por cada archivo nuevo, extrae el audio con `ffmpeg` y lo divide en segmentos de 10 minutos (límite típico de las APIs gratuitas).
3. Intenta transcribir cada segmento probando los proveedores en orden hasta que uno responda OK:
   - **Groq** (`whisper-large-v3`)
   - **Gladia**
   - **Deepgram** (`nova-2`, español)
4. Si un proveedor devuelve `429 (rate limit)`, salta al siguiente.
5. Une los segmentos y escribe un `.vtt` en `transcriptions/`.
6. Mueve el original a `procesados/` y registra el nombre en `done_transcriptions.txt` para no repetir.

### Diseño para correr por cron

El script se ejecuta cada minuto vía cron. Para evitar que dos instancias procesen el mismo archivo (gastando cuota gratuita 2×) usa **locks por archivo** con `fcntl.flock`:

- Cada instancia toma **un único archivo**, lo procesa y termina.
- Si hay un segundo archivo, la siguiente instancia (el próximo minuto, o una en paralelo) lo toma sin pisar el primero.
- Los locks viven en `/tmp/transcripcion_locks/<sha1>.lock` y se liberan al terminar (o al morir el proceso, por el comportamiento de `flock`).

## Requisitos

- Linux con `ffmpeg` instalado (`apt install ffmpeg`)
- Python 3.10+
- Cuentas gratuitas en al menos uno de:
  - [Groq](https://console.groq.com/) (recomendado por velocidad)
  - [Gladia](https://www.gladia.io/)
  - [Deepgram](https://console.deepgram.com/)

## Instalación

```bash
git clone git@github.com:daxcoletti/meet-transcriptions.git
cd meet-transcriptions

python3 -m venv venv
source venv/bin/activate
pip install requests tqdm
```

## Configuración

1. **API keys**: cada proveedor lee su key desde un archivo en la raíz del repo (que está en `.gitignore`):

   ```bash
   echo "tu-groq-api-key"     > groq.key
   echo "tu-gladia-api-key"   > gladia.key
   echo "tu-deepgram-api-key" > deepgram.key
   ```

   Solo hace falta tener al menos uno; los faltantes se omiten automáticamente.

2. **Rutas** (editar al inicio de `super_transcriptor_v2.py` si querés otras):

   ```python
   AUDIOS_DIR          = Path("/home/dax/Audios")
   TRANSCRIPTIONS_DIR  = AUDIOS_DIR / "transcriptions"
   PROCESSED_DIR       = AUDIOS_DIR / "procesados"
   LOG_FILE            = AUDIOS_DIR / "done_transcriptions.txt"
   ```

   `transcriptions/`, `procesados/` y el log se crean solos en la primera corrida.

## Uso manual

```bash
source venv/bin/activate
python super_transcriptor_v2.py
```

Procesa **un** archivo y termina (por diseño, para que múltiples instancias paralelas tomen distintos archivos).

## Uso por cron (recomendado)

`run_transcription.sh` activa el venv y redirige stdout/stderr al log. Agregar al crontab del usuario:

```bash
crontab -e
```

```cron
* * * * * /home/dax/dev/meet-transcriptions/run_transcription.sh
```

Con esto, cron lanza una instancia por minuto. Si todavía está corriendo la anterior, la nueva tomará el siguiente archivo libre o terminará silenciosamente diciendo que no hay nada por hacer.

## Estructura del repo

```
.
├── super_transcriptor_v2.py    # Script principal
├── run_transcription.sh        # Wrapper para cron (activa venv + ejecuta)
├── .gitignore
└── README.md
```

## Salida

Para `Reunion 2026-04-28.mkv` se genera:

- `transcriptions/Reunion 2026-04-28.vtt` — formato WebVTT
- `Minutas/Reunion 2026-04-28.md` — placeholder vacío para escribir la minuta a mano
- el archivo original se mueve a `procesados/`
- el nombre queda registrado en `done_transcriptions.txt`

## Errores comunes

- **`subprocess.DEVNULL` no existe** → tu Python es <3.3. Usar 3.10+.
- **`ffmpeg: not found`** → instalar con `apt install ffmpeg`.
- **El VTT sale vacío y el archivo se movió a procesados** → bug de versiones previas a este fix; actualizar a `super_transcriptor_v2.py` actual (valida que `ffmpeg` haya generado segmentos antes de marcar como completo).
- **Cron no encuentra `python`** → usar `run_transcription.sh` que activa el venv, o poner la ruta absoluta al python del venv en el crontab.

## Licencia

Uso personal.
