"""Grabación de pantalla integrada (fase 1a+1b: Windows y Linux/X11).

Diseño:
- Resolución y FPS moderados: suficiente fluidez para volver a ver la
  reunión sin que se entrecorte, manteniendo archivos chicos y poca CPU
  (el contenido es casi estático y x264 comprime muy bien frames repetidos).
- Contenedor MKV: si la app muere a mitad de una grabación larga, el archivo
  queda reproducible hasta el corte (un MP4 sin finalizar es basura).
- Se graba en un staging (<carpeta vigilada>/.grabando/) y se mueve a la
  carpeta vigilada al detener: así el watcher recién lo ve terminado y lo
  manda al pipeline de transcripción como cualquier otro archivo.
- ffmpeg se detiene mandándole 'q' por stdin (finaliza el MKV bien).

Por plataforma:
- Linux/X11: un solo proceso ffmpeg — x11grab (video) + pulse default (mic)
  + pulse <sink>.monitor (audio del sistema: lo que suena en los parlantes,
  o sea el resto de la reunión) mezclados con amix.
- Windows: ffmpeg gdigrab (video) + PyAudioWPatch para micrófono y loopback
  WASAPI (ffmpeg no captura loopback en Windows); al detener se muxea todo.
- Wayland: fase futura (portal ScreenCast + PipeWire). session_kind() lo
  detecta para que la GUI avise en vez de grabar una pantalla negra.
"""

import collections
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

from . import ffmpeg_utils

# calidad → (alto de video, fps)
# 10 fps es el piso para que la reproducción no se sienta entrecortada;
# menos de eso servía para identificar pantallas pero no para volver a ver
# la reunión. El costo en disco/CPU sigue siendo bajo: el contenido es casi
# estático y x264 con -tune stillimage comprime muy bien los frames repetidos.
QUALITY = {
    "low": (480, 10),
    "medium": (720, 15),
    "high": (1080, 30),
}

STAGING_DIRNAME = ".grabando"


class RecordingError(Exception):
    pass


def session_kind():
    """"windows" | "x11" | "wayland" | "unknown" — qué backend corresponde."""
    if os.name == "nt":
        return "windows"
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if session == "x11" or os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def _default_pulse_monitor():
    """Fuente monitor del sink por defecto (audio del sistema), o None."""
    try:
        proc = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, text=True, timeout=10,
            env=ffmpeg_utils.subprocess_env(),
        )
        sink = proc.stdout.strip()
        return f"{sink}.monitor" if proc.returncode == 0 and sink else None
    except (OSError, subprocess.TimeoutExpired):
        return None


class _StreamWriter(threading.Thread):
    """Vuelca a WAV un stream de audio YA ABIERTO (mic o loopback).

    Los streams se abren secuencialmente en el hilo principal con UNA sola
    instancia de PyAudio: Pa_Initialize no es thread-safe, y crear dos
    instancias en hilos paralelos crashea el proceso (visto en Windows).
    Este hilo solo hace read() → writeframes().
    """

    def __init__(self, kind, stream, out_path, channels, rate):
        super().__init__(daemon=True, name=f"audio-{kind}")
        self.kind = kind  # "mic" | "loopback"
        self.stream = stream
        self.out_path = Path(out_path)
        self.channels = channels
        self.rate = rate
        self.error = None
        # OJO: no llamar "_stop" a este atributo — Thread tiene un método
        # privado _stop() que join() invoca; pisarlo rompe al detener.
        self._halt = threading.Event()

    def stop(self):
        self._halt.set()

    def run(self):
        try:
            frame_bytes = self.channels * 2  # paInt16
            written = 0
            t0 = time.monotonic()
            with wave.open(str(self.out_path), "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.rate)
                while not self._halt.is_set():
                    avail = self.stream.get_read_available()
                    if avail > 0:
                        n = min(avail, 4096)
                        wf.writeframes(
                            self.stream.read(n, exception_on_overflow=False)
                        )
                        written += n
                    else:
                        # Un loopback WASAPI NO entrega frames mientras no
                        # suena nada: un read() acá se bloquearía para
                        # siempre (y liberar PortAudio con un read bloqueado
                        # tumba el proceso — visto en crash.log). Dormir y
                        # rellenar con silencio para mantener la línea de
                        # tiempo (que el mute no desincronice la mezcla).
                        time.sleep(0.05)
                        expected = int((time.monotonic() - t0) * self.rate)
                        deficit = expected - written
                        if deficit > self.rate // 4:  # >250 ms sin datos
                            pad = min(deficit, self.rate)  # de a 1 s máximo
                            wf.writeframes(b"\x00" * (pad * frame_bytes))
                            written += pad
            self.stream.stop_stream()
            self.stream.close()
        except Exception as e:
            self.error = f"{self.kind}: {e}"


def kill_orphan_ffmpeg(cfg, log=None):
    """Mata ffmpeg huérfanos de sesiones anteriores que siguen grabando.

    Si la app crashea sin detener ffmpeg, ese proceso sigue grabando la
    pantalla indefinidamente y mantiene agarrados los archivos de staging
    (impide recuperarlos). Se identifican porque su línea de comandos apunta
    a nuestro directorio .grabando/.
    """
    log = log or (lambda m: None)
    marker = str(cfg.audios_dir / STAGING_DIRNAME)
    pids = []
    try:
        if os.name == "nt":
            quoted = marker.replace("'", "''")
            script = (
                "Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like '*{quoted}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=30,
                **ffmpeg_utils.SUBPROCESS_FLAGS,
            )
            pids = [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]
        else:
            proc = subprocess.run(
                ["pgrep", "-f", f"ffmpeg.*{marker}"],
                capture_output=True, text=True, timeout=10,
                env=ffmpeg_utils.subprocess_env(),
            )
            pids = [p for p in proc.stdout.split() if p]
            for pid in pids:
                subprocess.run(["kill", pid], capture_output=True, timeout=10)
        if pids:
            log(
                f"🧹 Cerré {len(pids)} grabación(es) huérfana(s) de una sesión "
                f"anterior (PID {', '.join(pids)})."
            )
            time.sleep(1.5)  # que el SO libere los archivos antes de recuperar
    except Exception as e:
        log(f"⚠️  no pude buscar ffmpeg huérfanos: {e}")


def recover_orphans(cfg, log=None):
    """Rescata grabaciones que quedaron en .grabando/ por un crash o cierre.

    Se llama al iniciar la app (antes de cualquier grabación nueva, así no
    hay riesgo de tocar una grabación activa). Si hay WAVs de audio junto al
    video, intenta muxearlos; si no se puede, salva el video solo.
    """
    log = log or (lambda m: None)
    staging = cfg.audios_dir / STAGING_DIRNAME
    if not staging.is_dir():
        return

    # Mux ya hecho pero move interrumpido
    for f in sorted(staging.glob("final_*.mkv")):
        stamp = f.stem.replace("final_video_", "")
        target = cfg.audios_dir / f"Grabacion_recuperada_{stamp}.mkv"
        try:
            shutil.move(str(f), str(target))
            log(f"♻️  Grabación recuperada: {target.name}")
        except OSError as e:
            log(f"⚠️  no pude recuperar {f.name}: {e}")

    for v in sorted(staging.glob("video_*.mkv")):
        if v.stat().st_size == 0:
            continue
        stamp = v.stem.replace("video_", "")
        wavs = sorted(
            p for p in staging.glob(f"*_{stamp}.wav") if p.stat().st_size > 44
        )
        target = cfg.audios_dir / f"Grabacion_recuperada_{stamp}.mkv"
        out = v
        if wavs:
            rec = ScreenRecorder(cfg, log=log)
            rec._video_path = v
            rec._staging = staging
            try:
                merged = staging / f"rescate_{stamp}.mkv"
                rec._mux(wavs[:2], merged)
                out = merged
            except Exception as e:
                log(f"⚠️  recuperación: no pude unir el audio ({e}); salvo solo el video.")
        try:
            shutil.move(str(out), str(target))
            log(f"♻️  Grabación recuperada: {target.name}")
        except OSError as e:
            log(f"⚠️  no pude recuperar {v.name}: {e}")

    # Limpiar sobras (WAVs sueltos, temporales)
    for f in staging.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass


class ScreenRecorder:
    """Una grabación por vez. start() → grabar → stop() devuelve el archivo final."""

    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or (lambda msg: None)
        self._proc = None
        self._pa = None
        self._taps = []
        self._stderr_tail = collections.deque(maxlen=60)
        self._t0 = None
        self._staging = None
        self._video_path = None
        self._final_name = None

    @property
    def recording(self):
        return self._proc is not None

    def elapsed(self):
        return int(time.time() - self._t0) if self._t0 else 0

    # ------------------------------------------------------------------
    def start(self, screen_size=None):
        """Arranca la grabación. screen_size=(w, h) es obligatorio en X11."""
        if self.recording:
            raise RecordingError("ya hay una grabación en curso")

        kind = session_kind()
        if kind == "wayland":
            raise RecordingError("wayland")
        if kind == "unknown":
            raise RecordingError("no se detectó una sesión gráfica")

        ffmpeg = ffmpeg_utils.find_ffmpeg(self.cfg)
        if not ffmpeg:
            raise RecordingError("ffmpeg no está disponible")

        height, fps = QUALITY.get(self.cfg.data.get("record_quality", "medium"), QUALITY["medium"])
        want_mic = bool(self.cfg.data.get("record_mic", True))
        want_system = bool(self.cfg.data.get("record_system", True))

        self._staging = self.cfg.audios_dir / STAGING_DIRNAME
        self._staging.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        self._final_name = f"Grabacion_{stamp}.mkv"
        self._video_path = self._staging / f"video_{stamp}.mkv"

        if kind == "x11":
            cmd = self._build_x11_cmd(ffmpeg, height, fps, want_mic, want_system, screen_size)
        else:
            cmd = self._build_gdigrab_cmd(ffmpeg, height, fps)

        self.log(f"▶ grabación ({kind}, {height}p/{fps}fps): {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=ffmpeg_utils.subprocess_env(),
            **ffmpeg_utils.SUBPROCESS_FLAGS,
        )

        # Drenar stderr SIEMPRE: si nadie lee el pipe y ffmpeg escribe
        # suficiente, se llena y ffmpeg se congela. Guardamos la cola para
        # diagnóstico.
        self._stderr_tail = collections.deque(maxlen=60)

        def _drain(proc=self._proc, tail=self._stderr_tail):
            for line in iter(proc.stderr.readline, b""):
                tail.append(line.decode("utf-8", "replace"))

        threading.Thread(target=_drain, daemon=True, name="ffmpeg-stderr").start()

        # En Windows el audio va por hilos propios (WASAPI); en X11 ya está
        # todo dentro del comando ffmpeg.
        if kind == "windows" and (want_mic or want_system):
            self._start_windows_audio(want_mic, want_system, stamp)

        # Si ffmpeg muere en el arranque (args malos, display inaccesible),
        # detectarlo ya y no simular que grabamos.
        time.sleep(1.0)
        if self._proc.poll() is not None:
            err = "".join(self._stderr_tail)[-400:]
            self._cleanup_taps()
            self._proc = None
            raise RecordingError(f"ffmpeg no arrancó: {err}")

        self._t0 = time.time()

    def video_died(self):
        """True si ffmpeg terminó solo mientras 'grabábamos' (para que la GUI
        dispare el rescate: stop() salva lo grabado hasta el corte)."""
        return self._proc is not None and self._proc.poll() is not None

    def _start_windows_audio(self, want_mic, want_system, stamp):
        """Abre mic y/o loopback WASAPI y lanza sus hilos de volcado.

        Todo secuencial y con UNA instancia de PyAudio (Pa_Initialize no es
        thread-safe). Cualquier fallo degrada a grabar sin ese audio, nunca
        aborta el video.
        """
        try:
            import pyaudiowpatch as pyaudio
        except Exception as e:
            self.log(f"⚠️  audio: PyAudioWPatch no disponible ({e}); grabo sin audio.")
            return
        try:
            self._pa = pyaudio.PyAudio()
        except Exception as e:
            self.log(f"⚠️  audio: PortAudio no inicializó ({e}); grabo sin audio.")
            return

        wanted = []
        if want_mic:
            try:
                wanted.append(("mic", self._pa.get_default_input_device_info()))
            except Exception as e:
                self.log(f"⚠️  sin micrófono por defecto: {e}")
        if want_system:
            try:
                wanted.append(("loopback", self._pa.get_default_wasapi_loopback()))
            except Exception as e:
                self.log(f"⚠️  sin loopback WASAPI (audio del sistema): {e}")

        for kind_a, dev in wanted:
            try:
                rate = int(dev["defaultSampleRate"])
                channels = max(1, int(dev["maxInputChannels"]))
                self.log(
                    f"🎙 audio {kind_a}: «{dev.get('name')}» "
                    f"(idx {dev.get('index')}, {rate} Hz, {channels} ch)"
                )
                stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=rate,
                    input=True,
                    input_device_index=int(dev["index"]),
                    frames_per_buffer=1024,
                )
                writer = _StreamWriter(
                    kind_a, stream, self._staging / f"{kind_a}_{stamp}.wav",
                    channels, rate,
                )
                writer.start()
                self._taps.append(writer)
            except Exception as e:
                self.log(f"⚠️  no pude abrir el audio {kind_a}: {e}")

    # ------------------------------------------------------------------
    def stop(self):
        """Detiene, muxea si hace falta y mueve el resultado a la carpeta
        vigilada. Devuelve la ruta final. Puede tardar unos segundos."""
        if not self.recording:
            raise RecordingError("no hay grabación en curso")
        proc, self._proc = self._proc, None
        self._t0 = None

        try:
            proc.stdin.write(b"q")
            proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=10)

        audio_files = []
        errors = []
        alive = []
        for t in self._taps:
            t.stop()
        for t in self._taps:
            t.join(timeout=10)
            if t.is_alive():
                # Sigue clavado en una lectura nativa: NO tocar su archivo.
                alive.append(t.kind)
                continue
            if t.error:
                errors.append(t.error)
                self.log(f"⚠️  audio {t.kind}: {t.error}")
            elif t.out_path.exists() and t.out_path.stat().st_size > 44:
                audio_files.append(t.out_path)
        self._taps = []
        if self._pa is not None:
            if alive:
                # Liberar PortAudio con un read() en curso = access violation
                # (crash.log de Windows). Mejor filtrar la instancia: se va
                # con el proceso.
                self.log(
                    f"⚠️  audio {', '.join(alive)} no terminó a tiempo; "
                    f"no libero PortAudio para evitar un crash."
                )
            else:
                try:
                    self._pa.terminate()
                except Exception:
                    pass
            self._pa = None

        if not self._video_path.exists() or self._video_path.stat().st_size == 0:
            tail = "".join(self._stderr_tail)[-400:]
            detail = "; ".join(errors + ([f"ffmpeg: {tail}"] if tail else []))
            raise RecordingError("la grabación no produjo video" + (f" ({detail})" if detail else ""))

        if audio_files:
            merged = self._staging / f"final_{self._video_path.stem}.mkv"
            self._mux(audio_files, merged)
            source = merged
        else:
            source = self._video_path

        final = self.cfg.audios_dir / self._final_name
        shutil.move(str(source), str(final))
        self._cleanup_temps()
        return final

    # ------------------------------------------------------------------
    def _build_x11_cmd(self, ffmpeg, height, fps, want_mic, want_system, screen_size):
        if not screen_size:
            raise RecordingError("en X11 hace falta el tamaño de pantalla")
        w, h = screen_size
        display = os.environ.get("DISPLAY", ":0")
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-f", "x11grab", "-framerate", str(fps),
            "-video_size", f"{w}x{h}", "-i", display,
        ]
        audio_inputs = 0
        if want_mic:
            cmd += ["-f", "pulse", "-i", "default"]
            audio_inputs += 1
        if want_system:
            monitor = _default_pulse_monitor()
            if monitor:
                cmd += ["-f", "pulse", "-i", monitor]
                audio_inputs += 1
            else:
                self.log("⚠️  No pude detectar el monitor de audio del sistema (pactl); grabo sin él.")

        vf = f"[0:v]scale=-2:{height}[v]"
        cmd += ["-filter_complex"]
        if audio_inputs == 2:
            cmd += [f"{vf};[1:a]aresample=48000[a1];[2:a]aresample=48000[a2];"
                    f"[a1][a2]amix=inputs=2:duration=longest[a]"]
            maps = ["-map", "[v]", "-map", "[a]"]
        elif audio_inputs == 1:
            cmd += [vf]
            maps = ["-map", "[v]", "-map", "1:a"]
        else:
            cmd += [vf]
            maps = ["-map", "[v]"]
        cmd += maps + [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-tune", "stillimage", "-pix_fmt", "yuv420p",
        ]
        if audio_inputs:
            cmd += ["-c:a", "aac", "-b:a", "128k"]
        cmd += [str(self._video_path)]
        return cmd

    def _build_gdigrab_cmd(self, ffmpeg, height, fps):
        return [
            ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-f", "gdigrab", "-framerate", str(fps), "-i", "desktop",
            "-vf", f"scale=-2:{height}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-tune", "stillimage", "-pix_fmt", "yuv420p",
            str(self._video_path),
        ]

    def _mux(self, audio_files, out_path):
        """Windows: junta el video con los WAV de mic/loopback (mezclados)."""
        ffmpeg = ffmpeg_utils.find_ffmpeg(self.cfg)
        cmd = [ffmpeg, "-y", "-i", str(self._video_path)]
        for a in audio_files:
            cmd += ["-i", str(a)]
        if len(audio_files) == 2:
            cmd += [
                "-filter_complex",
                "[1:a]aresample=48000[a1];[2:a]aresample=48000[a2];"
                "[a1][a2]amix=inputs=2:duration=longest[a]",
                "-map", "0:v", "-map", "[a]",
            ]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k", str(out_path)]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env=ffmpeg_utils.subprocess_env(),
            **ffmpeg_utils.SUBPROCESS_FLAGS,
        )
        if proc.returncode != 0 or not out_path.exists():
            err = (proc.stderr or b"").decode("utf-8", "replace")[-400:]
            raise RecordingError(f"falló el mux de audio+video: {err}")

    def _cleanup_taps(self):
        for t in self._taps:
            t.stop()
        self._taps = []

    def _cleanup_temps(self):
        if not self._staging:
            return
        for f in self._staging.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
