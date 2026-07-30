"""Traducciones de la interfaz (castellano / inglés).

Tabla simple de strings en vez del toolchain de Qt Linguist: menos
infraestructura y las dos lenguas quedan a la vista en un solo lugar.

Uso:
    from .i18n import tr
    tr("keys.test")                      → "Probar" / "Test"
    tr("notify.done.body", name="x.mp3") → con .format(**kwargs)

El idioma se fija con set_language("es" | "en" | "auto"); "auto" resuelve
por el locale del sistema. Default: "es" (comportamiento histórico del CLI).
"""

_lang = "es"

STRINGS = {
    # --- Bandeja / app ---
    "tray.activity": {"es": "Ver actividad", "en": "View activity"},
    "tray.open_recordings": {"es": "Abrir carpeta de grabaciones", "en": "Open recordings folder"},
    "tray.open_transcriptions": {"es": "Abrir transcripciones", "en": "Open transcriptions"},
    "tray.open_minutas": {"es": "Abrir minutas", "en": "Open minutes"},
    "tray.pause": {"es": "Pausar procesamiento", "en": "Pause processing"},
    "tray.resume": {"es": "Reanudar procesamiento", "en": "Resume processing"},
    "tray.settings": {"es": "Configuración…", "en": "Settings…"},
    "tray.quit": {"es": "Salir", "en": "Quit"},
    "log.title": {"es": "Meet Transcriptions — Actividad", "en": "Meet Transcriptions — Activity"},
    "tray.tip_ok": {
        "es": "Meet Transcriptions — ✔ listo: transcripción y minuta configuradas",
        "en": "Meet Transcriptions — ✔ ready: transcription and minutes configured",
    },
    "tray.tip_no_minuta": {
        "es": "Meet Transcriptions — ⚠ transcribe, pero SIN minuta: falta key de Gemini o Groq (Configuración)",
        "en": "Meet Transcriptions — ⚠ transcribes, but NO minutes: missing Gemini or Groq key (Settings)",
    },
    "tray.tip_no_trans": {
        "es": "Meet Transcriptions — ⚠ falta una key de transcripción (Configuración)",
        "en": "Meet Transcriptions — ⚠ missing a transcription key (Settings)",
    },
    "tray.tip_no_keys": {
        "es": "Meet Transcriptions — ✘ sin API keys: no puede procesar nada (abrí Configuración)",
        "en": "Meet Transcriptions — ✘ no API keys: nothing can be processed (open Settings)",
    },
    "app.no_tray": {
        "es": "No hay bandeja del sistema disponible en este entorno.",
        "en": "No system tray is available in this environment.",
    },
    "log.watching": {
        "es": "👀 Vigilando {dir} (eventos nativos del sistema).",
        "en": "👀 Watching {dir} (native filesystem events).",
    },
    "log.no_ffmpeg": {
        "es": "⚠️  ffmpeg no está disponible: los audios nuevos van a fallar hasta instalarlo (ver Configuración).",
        "en": "⚠️  ffmpeg is not available: new audio files will fail until it is installed (see Settings).",
    },
    "log.settings_updated": {"es": "⚙️  Configuración actualizada.", "en": "⚙️  Settings updated."},
    "log.paused": {"es": "⏸  Procesamiento en pausa.", "en": "⏸  Processing paused."},
    "log.resumed": {"es": "▶️  Procesamiento reanudado.", "en": "▶️  Processing resumed."},
    "notify.done.title": {"es": "Transcripción lista", "en": "Transcription ready"},
    "notify.done.body": {
        "es": "{name}: transcripción y minuta generadas.",
        "en": "{name}: transcript and minutes generated.",
    },
    "notify.fail.title": {"es": "Transcripción fallida", "en": "Transcription failed"},
    "notify.fail.body": {
        "es": "{name}: no se pudo procesar (ver actividad).",
        "en": "{name}: could not be processed (see activity).",
    },
    "notify.nominuta.title": {
        "es": "Transcripción lista (SIN minuta)",
        "en": "Transcript ready (NO minutes)",
    },
    "notify.nominuta.body": {
        "es": "{name}: la transcripción está, pero la minuta no se generó. Cargá una API key de Gemini o Groq en Configuración.",
        "en": "{name}: the transcript is done, but the minutes were not generated. Add a Gemini or Groq API key in Settings.",
    },

    # --- Actualizaciones ---
    "upd.menu_check": {"es": "Buscar actualizaciones", "en": "Check for updates"},
    "upd.menu_update": {"es": "⬆ Actualizar a la versión {version}", "en": "⬆ Update to version {version}"},
    "upd.available.title": {"es": "Actualización disponible", "en": "Update available"},
    "upd.available.body": {
        "es": "Salió la versión {version} (tenés la {current}). Actualizá desde el menú del ícono de la bandeja.",
        "en": "Version {version} is out (you have {current}). Update from the tray icon menu.",
    },
    "upd.none.title": {"es": "Sin novedades", "en": "No updates"},
    "upd.none.body": {
        "es": "Ya estás en la última versión ({current}).",
        "en": "You are already on the latest version ({current}).",
    },
    "upd.error": {
        "es": "No se pudo buscar actualizaciones: {err}",
        "en": "Could not check for updates: {err}",
    },
    "upd.downloading": {
        "es": "⬇ Descargando la actualización {version}…",
        "en": "⬇ Downloading update {version}…",
    },
    "upd.installing.title": {"es": "Actualizando", "en": "Updating"},
    "upd.installing.body": {
        "es": "La aplicación se va a cerrar, actualizar y reabrir sola en unos segundos.",
        "en": "The application will close, update and reopen by itself in a few seconds.",
    },
    "upd.dl_error": {
        "es": "❌ La descarga de la actualización falló: {err}",
        "en": "❌ The update download failed: {err}",
    },

    # --- Formulario de keys ---
    "keys.section_transcription": {
        "es": "🎙 Transcripción — se necesita AL MENOS UNA",
        "en": "🎙 Transcription — AT LEAST ONE required",
    },
    "keys.section_minuta": {
        "es": "📝 Minuta — se necesita Gemini (recomendado) o Groq",
        "en": "📝 Minutes — Gemini (recommended) or Groq required",
    },
    "keys.minuta_warn": {
        "es": "⚠️ Sin una key de <b>Gemini</b> o <b>Groq</b> NO se genera la minuta (resumen, decisiones y tareas) — solo la transcripción.",
        "en": "⚠️ Without a <b>Gemini</b> or <b>Groq</b> key, the minutes (summary, decisions, action items) are NOT generated — only the transcript.",
    },
    "prov.deepgram": {"es": "Transcripción + diarización (preferido)", "en": "Transcription + diarization (preferred)"},
    "prov.gladia": {"es": "Transcripción + diarización", "en": "Transcription + diarization"},
    "prov.assemblyai": {"es": "Transcripción + diarización", "en": "Transcription + diarization"},
    "prov.elevenlabs": {"es": "Transcripción + diarización (Scribe)", "en": "Transcription + diarization (Scribe)"},
    "prov.speechmatics": {"es": "Transcripción + diarización", "en": "Transcription + diarization"},
    "prov.groq": {"es": "Transcripción Whisper — también sirve como minuta de respaldo", "en": "Whisper transcription — also works as fallback for minutes"},
    "prov.gemini": {"es": "Minuta (contexto de 1M tokens) — conseguila gratis en AI Studio", "en": "Minutes (1M-token context) — get it free at AI Studio"},
    "keys.placeholder": {"es": "(sin configurar)", "en": "(not set)"},
    "keys.toggle_tip": {"es": "Mostrar/ocultar la key", "en": "Show/hide the key"},
    "keys.test": {"es": "Probar", "en": "Test"},
    "keys.empty": {"es": "vacía", "en": "empty"},
    "keys.testing": {"es": "⏳ probando…", "en": "⏳ testing…"},
    "keys.valid": {"es": "✔ válida", "en": "✔ valid"},
    "keys.rejected": {"es": "✘ rechazada", "en": "✘ rejected"},
    "keys.unknown": {"es": "? sin verificar", "en": "? unverified"},

    # --- Validadores ---
    "val.unavailable": {"es": "Sin verificación disponible", "en": "No verification available"},
    "val.neterr": {"es": "No se pudo verificar (red): {err}", "en": "Could not verify (network): {err}"},
    "val.valid": {"es": "Key válida", "en": "Valid key"},
    "val.rejected": {"es": "Key rechazada ({code})", "en": "Key rejected ({code})"},
    "val.unexpected": {"es": "Respuesta inesperada ({code})", "en": "Unexpected response ({code})"},

    # --- Widget ffmpeg ---
    "ff.download": {"es": "⬇ Descargar ffmpeg automáticamente", "en": "⬇ Download ffmpeg automatically"},
    "ff.recheck": {"es": "Volver a comprobar", "en": "Check again"},
    "ff.found": {"es": "✔ ffmpeg encontrado:", "en": "✔ ffmpeg found:"},
    "ff.missing": {
        "es": "✘ No se encontró ffmpeg. La aplicación lo necesita para extraer y segmentar el audio.",
        "en": "✘ ffmpeg was not found. The application needs it to extract and segment audio.",
    },
    "ff.hint_win": {
        "es": "Podés descargarlo automáticamente con el botón de abajo (build oficial de gyan.dev, ~90 MB), o instalarlo vos mismo y volver a comprobar.",
        "en": "You can download it automatically with the button below (official gyan.dev build, ~90 MB), or install it yourself and check again.",
    },
    "ff.hint_linux": {
        "es": "Instalalo con tu gestor de paquetes (p.ej. <code>sudo apt install ffmpeg</code>) y tocá «Volver a comprobar», o usá la descarga automática (build estático de johnvansickle.com).",
        "en": "Install it with your package manager (e.g. <code>sudo apt install ffmpeg</code>) and click “Check again”, or use the automatic download (static build from johnvansickle.com).",
    },
    "ff.dl_failed": {"es": "✘ La descarga falló:", "en": "✘ Download failed:"},

    # --- Wizard ---
    "wiz.title": {"es": "Meet Transcriptions — Configuración inicial", "en": "Meet Transcriptions — Initial setup"},
    "wiz.intro.title": {"es": "Bienvenido a Meet Transcriptions", "en": "Welcome to Meet Transcriptions"},
    "wiz.intro.text": {
        "es": (
            "Esta aplicación vigila una carpeta de grabaciones (Google Meet, "
            "Zoom, llamadas…) y, por cada audio nuevo, genera automáticamente:"
            "<ul><li>la <b>transcripción</b> con identificación de hablantes "
            "(VTT, TXT y JSON), y</li><li>una <b>minuta</b> en Markdown con "
            "resumen, decisiones y tareas.</li></ul>"
            "Usa los planes <b>gratuitos</b> de varios servicios de "
            "transcripción, rotando entre ellos para esquivar los límites de "
            "cuota. En los próximos pasos vamos a verificar <b>ffmpeg</b>, "
            "cargar tus <b>API keys</b> y elegir la <b>carpeta</b> a vigilar."
        ),
        "en": (
            "This application watches a recordings folder (Google Meet, Zoom, "
            "calls…) and, for every new audio file, automatically generates:"
            "<ul><li>the <b>transcript</b> with speaker identification "
            "(VTT, TXT and JSON), and</li><li><b>meeting minutes</b> in "
            "Markdown with summary, decisions and action items.</li></ul>"
            "It uses the <b>free</b> tiers of several transcription services, "
            "rotating among them to dodge individual quota limits. In the next "
            "steps we will verify <b>ffmpeg</b>, load your <b>API keys</b> and "
            "choose the <b>folder</b> to watch."
        ),
    },
    "wiz.intro.lang": {"es": "Idioma / Language:", "en": "Idioma / Language:"},
    "lang.auto": {"es": "Automático (sistema)", "en": "Automatic (system)"},
    "wiz.ffmpeg.title": {"es": "Paso 1 · ffmpeg", "en": "Step 1 · ffmpeg"},
    "wiz.ffmpeg.subtitle": {
        "es": "ffmpeg es un programa externo (gratuito y de código abierto) que la aplicación usa para extraer y segmentar el audio.",
        "en": "ffmpeg is an external program (free and open source) that the application uses to extract and segment audio.",
    },
    "wiz.ffmpeg.skip": {
        "es": "Continuar sin ffmpeg (lo instalo yo más tarde)",
        "en": "Continue without ffmpeg (I'll install it later)",
    },
    "wiz.keys.title": {"es": "Paso 2 · API keys", "en": "Step 2 · API keys"},
    "wiz.keys.subtitle": {
        "es": (
            "Registrate gratis en los servicios que quieras (el nombre de cada "
            "uno es un enlace) y pegá acá sus API keys. Con UNA key de "
            "transcripción alcanza; cuantas más cargues, más cuota gratuita "
            "total y mejor tolerancia a fallos."
        ),
        "en": (
            "Sign up for free on the services you want (each name is a link) "
            "and paste their API keys here. ONE transcription key is enough; "
            "the more you add, the more total free quota and the better the "
            "fault tolerance."
        ),
    },
    "wiz.folder.title": {"es": "Paso 3 · Carpeta de grabaciones", "en": "Step 3 · Recordings folder"},
    "wiz.folder.subtitle": {
        "es": (
            "Esta es LA carpeta donde vas a arrastrar tus grabaciones: todo "
            "audio o video que aparezca acá se transcribe automáticamente. Los "
            "resultados quedan en subcarpetas (transcriptions/, Minutas/) y el "
            "original se mueve a procesados/."
        ),
        "en": (
            "This is THE folder where you will drag & drop your recordings: any "
            "audio or video file that appears here gets transcribed "
            "automatically. Results go to subfolders (transcriptions/, "
            "Minutas/) and the original is moved to procesados/."
        ),
    },
    "wiz.folder.browse": {"es": "Examinar…", "en": "Browse…"},
    "wiz.folder.dialog": {"es": "Elegí la carpeta de grabaciones", "en": "Choose the recordings folder"},
    "wiz.folder.drop_note": {
        "es": "💡 Para que la carpeta quede siempre a mano a la hora de arrastrar archivos:",
        "en": "💡 To keep the folder at hand when dragging files:",
    },
    "wiz.folder.desktop_link": {
        "es": "Crear un acceso directo en el Escritorio",
        "en": "Create a shortcut on the Desktop",
    },
    "wiz.folder.pin_win": {
        "es": "Anclar al Acceso rápido del Explorador de archivos",
        "en": "Pin to File Explorer's Quick access",
    },
    "wiz.folder.pin_linux": {
        "es": "Agregar a los marcadores del gestor de archivos",
        "en": "Add to the file manager bookmarks",
    },
    "wiz.final.title": {"es": "¡Listo!", "en": "All set!"},
    "wiz.final.autostart": {
        "es": "Iniciar Meet Transcriptions al encender el equipo",
        "en": "Start Meet Transcriptions when the computer starts",
    },
    "wiz.final.folder": {"es": "• Carpeta vigilada: <b>{folder}</b>", "en": "• Watched folder: <b>{folder}</b>"},
    "wiz.final.keys": {"es": "• API keys configuradas: <b>{n}</b>", "en": "• API keys configured: <b>{n}</b>"},
    "wiz.final.ffmpeg_ok": {"es": "• ffmpeg: <b>disponible ✔</b>", "en": "• ffmpeg: <b>available ✔</b>"},
    "wiz.final.ffmpeg_missing": {
        "es": '• ffmpeg: <b style="color:red">pendiente de instalar ✘</b>',
        "en": '• ffmpeg: <b style="color:red">pending install ✘</b>',
    },
    "wiz.final.shortcuts": {"es": "• Accesos a la carpeta: {what}", "en": "• Folder shortcuts: {what}"},
    "wiz.final.sc_desktop": {"es": "Escritorio", "en": "Desktop"},
    "wiz.final.sc_pin_win": {"es": "Acceso rápido", "en": "Quick access"},
    "wiz.final.sc_pin_linux": {"es": "marcadores", "en": "bookmarks"},
    "wiz.final.sc_none": {"es": "ninguno", "en": "none"},
    "wiz.final.text": {
        "es": (
            "Al finalizar, la aplicación queda en la <b>bandeja del sistema</b> "
            "(junto al reloj). Arrastrá tus grabaciones a la carpeta vigilada "
            "— o a su acceso directo — y en unos minutos vas a tener la "
            "transcripción y la minuta. Todo esto se puede cambiar después "
            "desde el menú «Configuración»."
        ),
        "en": (
            "When you finish, the application stays in the <b>system tray</b> "
            "(next to the clock). Drag your recordings into the watched folder "
            "— or its shortcut — and within minutes you will have the "
            "transcript and the minutes. Everything can be changed later from "
            "the “Settings” menu."
        ),
    },

    # --- Configuración ---
    "set.title": {"es": "Meet Transcriptions — Configuración", "en": "Meet Transcriptions — Settings"},
    "set.keys_group": {
        "es": "API keys (los nombres son enlaces para registrarse)",
        "en": "API keys (names are sign-up links)",
    },
    "set.general": {"es": "General", "en": "General"},
    "set.folder": {"es": "Carpeta vigilada:", "en": "Watched folder:"},
    "set.lang_speechmatics": {"es": "Idioma (Speechmatics):", "en": "Language (Speechmatics):"},
    "set.lang_speechmatics_tip": {
        "es": "Speechmatics no detecta idioma automáticamente: transcribe con un idioma fijo por trabajo.",
        "en": "Speechmatics does not auto-detect language: it transcribes with a fixed language per job.",
    },
    "set.ui_lang": {"es": "Idioma de la interfaz:", "en": "Interface language:"},
    "set.autostart": {"es": "Iniciar al encender el equipo", "en": "Start when the computer starts"},
    "set.shortcuts": {"es": "Accesos a la carpeta:", "en": "Folder shortcuts:"},
    "set.make_desktop": {"es": "Crear acceso en el Escritorio", "en": "Create Desktop shortcut"},
    "set.make_pin_win": {"es": "Anclar al Acceso rápido", "en": "Pin to Quick access"},
    "set.make_pin_linux": {"es": "Agregar a marcadores", "en": "Add to bookmarks"},
    "set.ffmpeg_group": {"es": "ffmpeg", "en": "ffmpeg"},
    "sc.ok": {"es": "Listo ✔", "en": "Done ✔"},
    "sc.fail": {"es": "No se pudo ✘", "en": "Failed ✘"},
}


def resolve(value):
    """'es'/'en' explícito, o 'auto'/None → locale del sistema."""
    if value in ("es", "en"):
        return value
    lang = ""
    try:
        from PySide6.QtCore import QLocale
        lang = QLocale.system().name()  # p.ej. "es_AR"
    except ImportError:
        import locale
        lang = (locale.getlocale()[0] or "")
    lang = lang.lower()
    return "es" if lang.startswith(("es", "spanish")) else "en"


def set_language(value):
    global _lang
    _lang = resolve(value)


def current():
    return _lang


def tr(key, **fmt):
    entry = STRINGS[key]
    s = entry.get(_lang) or entry["en"]
    return s.format(**fmt) if fmt else s
