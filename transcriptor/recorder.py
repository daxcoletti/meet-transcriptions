"""Grabación de pantalla integrada (fase 1a+1b: Windows y Linux/X11).

Diseño:
- Baja resolución y FPS bajísimos a propósito: el objetivo es identificar
  presentaciones y pantallas compartidas, no producir video lindo. Eso da
  archivos chicos y CPU despreciable.
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
QUALITY = {
    "low": (480, 2),
    "medium": (720, 5),
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


class _WasapiTap(threading.Thread):
    """Graba a WAV un dispositivo de audio de Windows (mic o loopback WASAPI)."""

    def __init__(self, kind, out_path):
        super().__init__(daemon=True, name=f"audio-{kind}")
        self.kind = kind  # "mic" | "loopback"
        self.out_path = Path(out_path)
        self.error = None
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            import pyaudiowpatch as pyaudio

            pa = pyaudio.PyAudio()
            try:
                if self.kind == "loopback":
                    dev = pa.get_default_wasapi_loopback()
                else:
                    dev = pa.get_default_input_device_info()
                rate = int(dev["defaultSampleRate"])
                channels = max(1, int(dev["maxInputChannels"]))
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=rate,
                    input=True,
                    input_device_index=dev["index"],
                    frames_per_buffer=1024,
                )
                with wave.open(str(self.out_path), "wb") as wf:
                    wf.setnchannels(channels)
                    wf.setsampwidth(2)  # paInt16
                    wf.setframerate(rate)
                    while not self._stop.is_set():
                        wf.writeframes(
                            stream.read(1024, exception_on_overflow=False)
                        )
                stream.stop_stream()
                stream.close()
            finally:
                pa.terminate()
        except Exception as e:
            self.error = f"{self.kind}: {e}"


class ScreenRecorder:
    """Una grabación por vez. start() → grabar → stop() devuelve el archivo final."""

    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or (lambda msg: None)
        self._proc = None
        self._taps = []
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

        height, fps = QUALITY.get(self.cfg.data.get("record_quality", "low"), QUALITY["low"])
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

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=ffmpeg_utils.subprocess_env(),
            **ffmpeg_utils.SUBPROCESS_FLAGS,
        )

        # En Windows el audio va por hilos propios (WASAPI); en X11 ya está
        # todo dentro del comando ffmpeg.
        if kind == "windows":
            stamp_dir = self._staging
            if want_mic:
                self._taps.append(_WasapiTap("mic", stamp_dir / f"mic_{stamp}.wav"))
            if want_system:
                self._taps.append(_WasapiTap("loopback", stamp_dir / f"sys_{stamp}.wav"))
            for t in self._taps:
                t.start()

        # Si ffmpeg muere en el arranque (args malos, display inaccesible),
        # detectarlo ya y no simular que grabamos.
        time.sleep(1.0)
        if self._proc.poll() is not None:
            err = (self._proc.stderr.read() or b"").decode("utf-8", "replace")[-400:]
            self._cleanup_taps()
            self._proc = None
            raise RecordingError(f"ffmpeg no arrancó: {err}")

        self._t0 = time.time()

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
        for t in self._taps:
            t.stop()
        for t in self._taps:
            t.join(timeout=10)
            if t.error:
                errors.append(t.error)
                self.log(f"⚠️  audio {t.kind}: {t.error}")
            elif t.out_path.exists() and t.out_path.stat().st_size > 44:
                audio_files.append(t.out_path)
        self._taps = []

        if not self._video_path.exists() or self._video_path.stat().st_size == 0:
            raise RecordingError("la grabación no produjo video" + (f" ({'; '.join(errors)})" if errors else ""))

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
            ffmpeg, "-y",
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
            cmd += [f"{vf};[1:a][2:a]amix=inputs=2:duration=longest[a]"]
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
            ffmpeg, "-y",
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
                "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=longest[a]",
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
